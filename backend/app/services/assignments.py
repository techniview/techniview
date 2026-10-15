from datetime import UTC, datetime

from sqlalchemy import select

from ..core.authorization import require_active_course
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
    ProblemState,
)
from .summaries import refresh_course_problem


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def load_assignment(db, course_id, assignment_id, *, writable=False):
    if writable:
        require_active_course(db, course_id)
    assignment = db.scalar(
        select(Assignment)
        .where(Assignment.id == assignment_id, Assignment.course_id == course_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if assignment is None:
        raise ApiError(404, "assignment_not_found", "Assignment not found.")
    if writable and assignment.state == AssignmentState.ARCHIVED:
        raise ApiError(
            409, "assignment_archived", "Archived assignments are read-only."
        )
    return assignment


def validate_dates(assignment):
    if (
        assignment.available_at
        and assignment.due_at
        and assignment.due_at < assignment.available_at
    ):
        raise ApiError(
            422, "invalid_assignment_dates", "Due date must follow availability."
        )


def student_memberships(db, course_id, ids=None):
    query = select(CourseMembership).where(
        CourseMembership.course_id == course_id,
        CourseMembership.role == MembershipRole.STUDENT,
        CourseMembership.withdrawn_at.is_(None),
    )
    if ids is not None:
        if len(ids) != len(set(ids)) or any(i <= 0 for i in ids):
            raise ApiError(
                422, "invalid_recipients", "Recipient IDs must be unique positive IDs."
            )
        query = query.where(CourseMembership.id.in_(ids))
    rows = list(db.scalars(query.with_for_update()).all())
    if ids is not None and len(rows) != len(ids):
        raise ApiError(
            422,
            "invalid_recipients",
            "Recipients must be active students in this course.",
        )
    return rows


def replace_items(db, assignment, items, owner_id):
    ids = [i.problem_id for i in items]
    if len(ids) != len(set(ids)):
        raise ApiError(
            422, "duplicate_problem", "An assignment cannot repeat a problem."
        )
    problems = list(
        db.scalars(select(Problem).where(Problem.id.in_(ids)).with_for_update()).all()
    )
    if len(problems) != len(ids) or any(
        p.state != ProblemState.PUBLISHED
        or (p.owner_id is not None and p.owner_id != owner_id)
        for p in problems
    ):
        raise ApiError(
            404,
            "problem_not_found",
            "Only published built-in or owned problems can be assigned.",
        )
    for item in list(assignment.items):
        db.delete(item)
    db.flush()
    assignment.items = [
        AssignmentItem(
            problem_id=i.problem_id,
            item_order=n,
            points=i.points,
            submission_limit=i.submission_limit,
        )
        for n, i in enumerate(items, 1)
    ]
    db.flush()
    for item in assignment.items:
        db.refresh(item)


def audit(db, assignment, actor_id, action, before, after):
    db.add(
        AssignmentAudit(
            assignment_id=assignment.id,
            actor_membership_id=actor_id,
            action=action,
            before=before,
            after=after,
        )
    )


def refresh_summaries(db, assignment):
    db.flush()
    for pid in sorted({i.problem_id for i in assignment.items}):
        refresh_course_problem(db, assignment.course_id, pid)


def publish(db, assignment, actor_id):
    if assignment.state != AssignmentState.DRAFT:
        raise ApiError(409, "assignment_not_draft", "Only drafts can be published.")
    if not assignment.items:
        raise ApiError(422, "empty_assignment", "Assignment must contain a problem.")
    validate_dates(assignment)
    # Recheck frozen content in the publication transaction.
    for item in assignment.items:
        problem = db.get(Problem, item.problem_id)
        if problem.state != ProblemState.PUBLISHED:
            raise ApiError(
                409,
                "problem_unavailable",
                "An assignment problem is no longer published.",
            )
    students = student_memberships(
        db,
        assignment.course_id,
        assignment.selected_membership_ids
        if assignment.recipient_mode == "selected"
        else None,
    )
    for member in students:
        db.add(
            AssignmentRecipient(
                assignment_id=assignment.id,
                membership_id=member.id,
                course_id=assignment.course_id,
            )
        )
    assignment.state = AssignmentState.PUBLISHED
    audit(
        db,
        assignment,
        actor_id,
        "publish",
        {},
        {"membership_ids": [m.id for m in students]},
    )
    refresh_summaries(db, assignment)


def change_recipients(db, assignment, body, actor_id):
    if assignment.state != AssignmentState.PUBLISHED:
        raise ApiError(
            409, "assignment_not_published", "Publish before changing recipients."
        )
    students = student_memberships(db, assignment.course_id, body.add_membership_ids)
    existing = {
        r.membership_id: r
        for r in db.scalars(
            select(AssignmentRecipient)
            .where(AssignmentRecipient.assignment_id == assignment.id)
            .with_for_update()
        )
    }
    before = sorted(mid for mid, r in existing.items() if r.removed_at is None)
    if any(mid not in existing for mid in body.remove_membership_ids):
        raise ApiError(422, "invalid_recipients", "Cannot remove an unknown recipient.")
    for member in students:
        if member.id in existing:
            existing[member.id].removed_at = None
        else:
            row = AssignmentRecipient(
                assignment_id=assignment.id,
                membership_id=member.id,
                course_id=assignment.course_id,
            )
            db.add(row)
            existing[member.id] = row
    for mid in body.remove_membership_ids:
        existing[mid].removed_at = now()
    after = sorted(mid for mid, r in existing.items() if r.removed_at is None)
    audit(
        db,
        assignment,
        actor_id,
        "recipients",
        {"membership_ids": before},
        {"membership_ids": after},
    )
    refresh_summaries(db, assignment)
