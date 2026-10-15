from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..core.authorization import get_membership, require_active_course
from ..core.dependencies import (
    CurrentUser,
    DbSession,
    InstructorMembership,
    StaffMembership,
)
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentAudit,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    MembershipRole,
    Problem,
    QuestionSet,
    QuestionSetState,
)
from ..schemas.assignment_management import (
    AssignmentCreate,
    AssignmentEdit,
    AssignmentItemInput,
    RecipientChange,
)
from ..schemas.contracts import AssignmentListResponse, AssignmentResponse
from ..services.assignments import (
    audit,
    change_recipients,
    load_assignment,
    publish,
    replace_items,
    student_memberships,
    validate_dates,
)
from ..services.presentation import assignment_response
from ..services.reporting import grade_rows

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
    if membership.withdrawn_at is None and membership.role in (
        MembershipRole.INSTRUCTOR,
        MembershipRole.TA,
    ):
        return True
    now = datetime.now(UTC).replace(tzinfo=None)
    if assignment.available_at is not None and assignment.available_at > now:
        return False
    if assignment.state == AssignmentState.DRAFT:
        return False
    return db.scalar(
        select(
            exists().where(
                AssignmentRecipient.assignment_id == assignment.id,
                AssignmentRecipient.membership_id == membership.id,
                AssignmentRecipient.removed_at.is_(None),
            )
        )
    )


@router.post("", response_model=AssignmentResponse, status_code=201)
def create_assignment_from_question_set(
    course_id: int,
    body: AssignmentCreate,
    db: DbSession,
    user: CurrentUser,
    membership: InstructorMembership,
):
    require_active_course(db, course_id)
    items = body.items
    if body.question_set_id is not None:
        question_set = db.scalar(
            select(QuestionSet).where(
                QuestionSet.id == body.question_set_id, QuestionSet.owner_id == user.id
            )
        )
        if question_set is None or question_set.state != QuestionSetState.PUBLISHED:
            raise ApiError(404, "question_set_not_found", "Question set not found.")
        items = [
            AssignmentItemInput(problem_id=i.problem_id) for i in question_set.items
        ]
    assignment = Assignment(
        course_id=course_id,
        assigned_by_membership_id=membership.id,
        source_question_set_id=body.question_set_id,
        title=body.title,
        description=body.description,
        state=AssignmentState.DRAFT,
        available_at=body.available_at,
        due_at=body.due_at,
        recipient_mode=body.recipient_mode,
        selected_membership_ids=body.selected_membership_ids,
    )
    validate_dates(assignment)
    if body.recipient_mode == "selected":
        student_memberships(db, course_id, body.selected_membership_ids)
    db.add(assignment)
    db.flush()
    replace_items(db, assignment, items, user.id)
    db.commit()
    return assignment_response(assignment)


@router.patch("/{assignment_id}", response_model=AssignmentResponse)
def edit_assignment(
    course_id: int,
    assignment_id: int,
    body: AssignmentEdit,
    db: DbSession,
    user: CurrentUser,
    membership: InstructorMembership,
):
    assignment = load_assignment(db, course_id, assignment_id, writable=True)
    changes = body.model_dump(exclude_unset=True)
    frozen = {"items", "recipient_mode", "selected_membership_ids"}
    if assignment.state != AssignmentState.DRAFT and frozen & changes.keys():
        raise ApiError(
            409,
            "assignment_frozen",
            "Published items and limits cannot change. Edit recipients separately.",
        )
    before = {}
    after = {}
    for name in changes.keys() - {"items"}:
        previous = getattr(assignment, name)
        value = changes[name]
        before[name] = (
            previous.isoformat() if isinstance(previous, datetime) else previous
        )
        after[name] = value.isoformat() if isinstance(value, datetime) else value
        setattr(assignment, name, value)
    validate_dates(assignment)
    if assignment.state == AssignmentState.DRAFT:
        if assignment.recipient_mode == "selected":
            student_memberships(db, course_id, assignment.selected_membership_ids)
        if body.items is not None:
            before["items"] = [i.problem_id for i in assignment.items]
            replace_items(db, assignment, body.items, user.id)
            after["items"] = [i.model_dump(mode="json") for i in body.items]
    audit(db, assignment, membership.id, "edit", before, after)
    db.commit()
    return assignment_response(assignment)


@router.post("/{assignment_id}/publish", response_model=AssignmentResponse)
def publish_assignment(
    course_id: int,
    assignment_id: int,
    db: DbSession,
    user: CurrentUser,
    _membership: InstructorMembership,
):
    assignment = load_assignment(db, course_id, assignment_id, writable=True)
    publish(db, assignment, _membership.id)
    db.commit()
    return assignment_response(assignment)


@router.post("/{assignment_id}/recipients", status_code=204)
def edit_recipients(
    course_id: int,
    assignment_id: int,
    body: RecipientChange,
    db: DbSession,
    _membership: InstructorMembership,
):
    assignment = load_assignment(db, course_id, assignment_id, writable=True)
    change_recipients(db, assignment, body, _membership.id)
    db.commit()


@router.get("/{assignment_id}/recipients")
def get_recipients(
    course_id: int, assignment_id: int, db: DbSession, _membership: InstructorMembership
):
    load_assignment(db, course_id, assignment_id)
    return {
        "items": [
            {"membership_id": r.membership_id, "removed_at": r.removed_at}
            for r in db.scalars(
                select(AssignmentRecipient)
                .where(AssignmentRecipient.assignment_id == assignment_id)
                .order_by(AssignmentRecipient.membership_id)
            )
        ]
    }


@router.post("/{assignment_id}/archive", response_model=AssignmentResponse)
def archive_assignment(
    course_id: int, assignment_id: int, db: DbSession, _membership: InstructorMembership
):
    assignment = load_assignment(db, course_id, assignment_id, writable=True)
    if assignment.state == AssignmentState.DRAFT:
        raise ApiError(
            409,
            "assignment_not_published",
            "Only published assignments can be archived.",
        )
    assignment.state = AssignmentState.ARCHIVED
    audit(
        db,
        assignment,
        _membership.id,
        "archive",
        {"state": "published"},
        {"state": "archived"},
    )
    db.commit()
    return assignment_response(assignment)


@router.get("/{assignment_id}/audit")
def assignment_audit(
    course_id: int,
    assignment_id: int,
    db: DbSession,
    _membership: InstructorMembership,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    load_assignment(db, course_id, assignment_id)
    query = select(AssignmentAudit).where(
        AssignmentAudit.assignment_id == assignment_id
    )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(AssignmentAudit.id.desc()).offset(offset).limit(limit)
    )
    return {
        "items": [
            {
                "id": r.id,
                "actor_membership_id": r.actor_membership_id,
                "action": r.action,
                "before": r.before,
                "after": r.after,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{assignment_id}/grades")
def assignment_grades(
    course_id: int,
    assignment_id: int,
    db: DbSession,
    _membership: StaffMembership,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    assignment = load_assignment(db, course_id, assignment_id)
    if assignment.state == AssignmentState.DRAFT:
        raise ApiError(
            409, "assignment_not_published", "Publish before reading grades."
        )
    rows = grade_rows(db, course_id, assignment_id)
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.get("", response_model=AssignmentListResponse)
def list_assignments(
    course_id: int,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    membership = get_membership(db, course_id, user.id, include_withdrawn=True)
    query = _assignment_query(course_id).order_by(Assignment.created_at.desc())
    if membership.role == MembershipRole.STUDENT or membership.withdrawn_at is not None:
        query = query.where(
            Assignment.state != AssignmentState.DRAFT,
            or_(
                Assignment.available_at.is_(None),
                Assignment.available_at <= datetime.now(UTC).replace(tzinfo=None),
            ),
            exists().where(
                AssignmentRecipient.assignment_id == Assignment.id,
                AssignmentRecipient.membership_id == membership.id,
                AssignmentRecipient.removed_at.is_(None),
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
    membership = get_membership(db, course_id, user.id, include_withdrawn=True)
    assignment = db.scalar(
        _assignment_query(course_id).where(Assignment.id == assignment_id)
    )
    if assignment is None or not _can_view_assignment(assignment, membership, db):
        raise ApiError(404, "assignment_not_found", "Assignment not found.")
    return assignment_response(assignment)
