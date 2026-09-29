from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.authorization import get_membership
from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    MembershipRole,
    Problem,
)
from ..schemas.contracts import AssignmentListResponse, AssignmentResponse
from ..services.presentation import assignment_response

router = APIRouter(prefix="/courses/{course_id}/assignments", tags=["assignments"])


def _assignment_query(course_id: int):
    return (
        select(Assignment)
        .options(
            selectinload(Assignment.items)
            .selectinload(AssignmentItem.problem)
            .selectinload(Problem.tags)
        )
        .where(Assignment.course_id == course_id)
    )


def _can_view_assignment(
    assignment: Assignment,
    membership: CourseMembership,
    db: Session,
) -> bool:
    if membership.role in (MembershipRole.INSTRUCTOR, MembershipRole.TA):
        return True
    now = datetime.now(UTC).replace(tzinfo=None)
    if assignment.available_at is not None and assignment.available_at > now:
        return False
    if assignment.state != AssignmentState.PUBLISHED:
        return False
    return db.scalar(
        select(
            exists().where(
                AssignmentRecipient.assignment_id == assignment.id,
                AssignmentRecipient.membership_id == membership.id,
            )
        )
    )


@router.get("", response_model=AssignmentListResponse)
def list_assignments(
    course_id: int,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    membership = get_membership(db, course_id, user.id)
    query = _assignment_query(course_id).order_by(Assignment.created_at.desc())
    if membership.role == MembershipRole.STUDENT:
        query = query.where(
            Assignment.state == AssignmentState.PUBLISHED,
            or_(
                Assignment.available_at.is_(None),
                Assignment.available_at <= datetime.now(UTC).replace(tzinfo=None),
            ),
            exists().where(
                AssignmentRecipient.assignment_id == Assignment.id,
                AssignmentRecipient.membership_id == membership.id,
            ),
        )
    assignments = list(db.scalars(query).unique().all())
    return {
        "items": [
            assignment_response(item) for item in assignments[offset : offset + limit]
        ],
        "total": len(assignments),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{assignment_id}", response_model=AssignmentResponse)
def get_assignment(
    course_id: int,
    assignment_id: int,
    db: DbSession,
    user: CurrentUser,
):
    membership = get_membership(db, course_id, user.id)
    assignment = db.scalar(
        _assignment_query(course_id).where(Assignment.id == assignment_id)
    )
    if assignment is None or not _can_view_assignment(assignment, membership, db):
        raise ApiError(404, "assignment_not_found", "Assignment not found.")
    return assignment_response(assignment)
