from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.authorization import get_membership
from ..core.dependencies import CurrentUser, DbSession, InstructorMembership
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    MembershipRole,
    Problem,
    QuestionSet,
    QuestionSetState,
)
from ..schemas.contracts import AssignmentListResponse, AssignmentResponse
from ..services.presentation import assignment_response

router = APIRouter(prefix="/courses/{course_id}/assignments", tags=["assignments"])


class AssignmentFromQuestionSet(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str | None = None
    question_set_id: int = Field(gt=0)
    available_at: datetime | None = None
    due_at: datetime | None = None

    @field_validator("available_at", "due_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


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


@router.post("", response_model=AssignmentResponse, status_code=201)
def create_assignment_from_question_set(
    course_id: int,
    body: AssignmentFromQuestionSet,
    db: DbSession,
    user: CurrentUser,
    membership: InstructorMembership,
):
    question_set = db.scalar(
        select(QuestionSet)
        .options(selectinload(QuestionSet.items))
        .where(QuestionSet.id == body.question_set_id, QuestionSet.owner_id == user.id)
    )
    if question_set is None or question_set.state != QuestionSetState.PUBLISHED:
        raise ApiError(404, "question_set_not_found", "Question set not found.")
    if body.due_at and body.available_at and body.due_at < body.available_at:
        raise ApiError(
            422, "invalid_assignment_dates", "Due date must follow availability."
        )
    assignment = Assignment(
        course_id=course_id,
        assigned_by_membership_id=membership.id,
        source_question_set_id=question_set.id,
        title=body.title,
        description=body.description,
        state=AssignmentState.DRAFT,
        available_at=body.available_at,
        due_at=body.due_at,
    )
    assignment.items = [
        AssignmentItem(
            problem_id=item.problem_id, item_order=index, points=Decimal("1")
        )
        for index, item in enumerate(question_set.items, start=1)
    ]
    db.add(assignment)
    db.flush()
    students = db.scalars(
        select(CourseMembership).where(
            CourseMembership.course_id == course_id,
            CourseMembership.role == MembershipRole.STUDENT,
            CourseMembership.withdrawn_at.is_(None),
        )
    ).all()
    db.add_all(
        AssignmentRecipient(
            assignment_id=assignment.id,
            membership_id=student.id,
            course_id=course_id,
        )
        for student in students
    )
    db.commit()
    saved_assignment = db.scalar(
        _assignment_query(course_id).where(Assignment.id == assignment.id)
    )
    return assignment_response(saved_assignment)


@router.post("/{assignment_id}/publish", response_model=AssignmentResponse)
def publish_assignment(
    course_id: int,
    assignment_id: int,
    db: DbSession,
    user: CurrentUser,
    _membership: InstructorMembership,
):
    assignment = db.scalar(
        _assignment_query(course_id).where(Assignment.id == assignment_id)
    )
    if assignment is None:
        raise ApiError(404, "assignment_not_found", "Assignment not found.")
    if assignment.state != AssignmentState.DRAFT:
        raise ApiError(
            409, "assignment_not_draft", "Only draft assignments can be published."
        )
    if not assignment.items:
        raise ApiError(
            422, "empty_assignment", "Assignment must contain at least one problem."
        )
    assignment.state = AssignmentState.PUBLISHED
    db.commit()
    return assignment_response(assignment)


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
