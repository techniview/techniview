from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.authorization import require_active_course
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    ErrorCategory,
    MembershipRole,
    StudentAssignmentProgress,
    StudentPracticeProgress,
    Submission,
    SubmissionStatus,
    User,
)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def require_assigned_item(
    db: Session,
    student_id: int,
    problem_id: int,
    assignment_item_id: int,
) -> AssignmentItem:
    now = utc_now()
    course_id = db.scalar(
        select(Assignment.course_id)
        .join(AssignmentItem)
        .where(AssignmentItem.id == assignment_item_id)
    )
    if course_id is not None:
        require_active_course(db, course_id)
    row = db.execute(
        select(AssignmentItem, AssignmentRecipient)
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(
            AssignmentRecipient,
            AssignmentRecipient.assignment_id == Assignment.id,
        )
        .join(
            CourseMembership,
            CourseMembership.id == AssignmentRecipient.membership_id,
        )
        .where(
            AssignmentItem.id == assignment_item_id,
            AssignmentItem.problem_id == problem_id,
            Assignment.state == AssignmentState.PUBLISHED,
            or_(Assignment.available_at.is_(None), Assignment.available_at <= now),
            CourseMembership.user_id == student_id,
            CourseMembership.role == MembershipRole.STUDENT,
            CourseMembership.withdrawn_at.is_(None),
            AssignmentRecipient.removed_at.is_(None),
        )
        .with_for_update()
    ).first()
    if row is None:
        raise ApiError(
            404,
            "assignment_item_not_found",
            "Assignment item not found.",
        )
    return row[0]


def _locked_practice_progress(
    db: Session,
    student_id: int,
    problem_id: int,
) -> StudentPracticeProgress | None:
    return db.scalar(
        select(StudentPracticeProgress)
        .where(
            StudentPracticeProgress.student_id == student_id,
            StudentPracticeProgress.problem_id == problem_id,
        )
        .with_for_update()
    )


def _locked_assignment_progress(
    db: Session,
    student_id: int,
    assignment_item_id: int,
) -> StudentAssignmentProgress | None:
    return db.scalar(
        select(StudentAssignmentProgress)
        .where(
            StudentAssignmentProgress.student_id == student_id,
            StudentAssignmentProgress.assignment_item_id == assignment_item_id,
        )
        .with_for_update()
    )


def get_or_create_progress(
    db: Session,
    student_id: int,
    problem_id: int,
    assignment_item_id: int | None,
):
    from .summaries import refresh_course_problem

    now = utc_now()
    if assignment_item_id is not None:
        require_assigned_item(db, student_id, problem_id, assignment_item_id)
        _open_progress(
            db,
            StudentAssignmentProgress,
            {"student_id": student_id, "assignment_item_id": assignment_item_id},
            now,
        )
        progress = _locked_assignment_progress(
            db,
            student_id,
            assignment_item_id,
        )
        db.flush()
        item = db.get(AssignmentItem, assignment_item_id)
        course_id = db.get(Assignment, item.assignment_id).course_id
        refresh_course_problem(db, course_id, problem_id)
        return progress

    db.scalar(select(User.id).where(User.id == student_id).with_for_update())
    _open_progress(
        db,
        StudentPracticeProgress,
        {"student_id": student_id, "problem_id": problem_id},
        now,
    )
    progress = _locked_practice_progress(db, student_id, problem_id)
    return progress


def _open_progress(db: Session, model, key: dict[str, int], now: datetime) -> None:
    """Insert before locking, avoiding InnoDB gap locks on absent progress rows."""
    table = model.__table__
    values = {**key, "first_opened_at": now}
    dialect = db.bind.dialect.name
    if dialect == "mysql":
        stmt = mysql_insert(table).values(**values)
        stmt = stmt.on_duplicate_key_update(
            first_opened_at=func.coalesce(table.c.first_opened_at, now)
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(table).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=list(key),
            set_={"first_opened_at": func.coalesce(table.c.first_opened_at, now)},
        )
    else:
        raise RuntimeError(f"unsupported database dialect: {dialect}")
    db.execute(stmt)


def is_eligible(submission: Submission) -> bool:
    return not submission.is_late or submission.late_approved_at is not None


ERROR_COUNTER_FIELDS = {
    ErrorCategory.WRONG_ANSWER: "wrong_answer_count",
    ErrorCategory.COMPILE_ERROR: "compile_error_count",
    ErrorCategory.RUNTIME_ERROR: "runtime_error_count",
    ErrorCategory.TIMEOUT: "timeout_count",
    ErrorCategory.RESOURCE_LIMIT: "resource_limit_count",
}


def finalize_progress(db: Session, submission: Submission) -> None:
    from .summaries import refresh_course_problem

    if submission.status == SubmissionStatus.INFRASTRUCTURE_ERROR:
        return
    if submission.assignment_item_id is not None:
        progress = _locked_assignment_progress(
            db, submission.student_id, submission.assignment_item_id
        )
    else:
        progress = _locked_practice_progress(
            db, submission.student_id, submission.problem_id
        )
    if progress is None:
        raise RuntimeError("accepted submission has no reserved progress")
    now = submission.completed_at or utc_now()
    progress.valid_attempt_count += 1
    progress.retry_count = max(0, progress.valid_attempt_count - 1)
    progress.last_attempt_at = now
    if is_eligible(submission):
        score = submission.score or Decimal("0")
        progress.best_score = max(progress.best_score, score)
        if (
            submission.status == SubmissionStatus.PASSED
            and progress.first_passed_at is None
        ):
            progress.first_passed_at = now
    if submission.primary_error is not None:
        field = ERROR_COUNTER_FIELDS[submission.primary_error]
        setattr(progress, field, getattr(progress, field) + 1)
    if submission.assignment_item_id is not None:
        item = db.get(AssignmentItem, submission.assignment_item_id)
        db.flush()
        refresh_course_problem(
            db, db.get(Assignment, item.assignment_id).course_id, submission.problem_id
        )


def recompute_assignment_grade(
    db: Session, student_id: int, assignment_item_id: int
) -> None:
    from .summaries import refresh_course_problem

    progress = _locked_assignment_progress(db, student_id, assignment_item_id)
    if progress is None:
        return
    eligible = list(
        db.scalars(
            select(Submission)
            .where(
                Submission.student_id == student_id,
                Submission.assignment_item_id == assignment_item_id,
                Submission.status != SubmissionStatus.INFRASTRUCTURE_ERROR,
                Submission.completed_at.is_not(None),
                (Submission.is_late.is_(False))
                | (Submission.late_approved_at.is_not(None)),
            )
            .order_by(Submission.completed_at, Submission.id)
        ).all()
    )
    progress.best_score = max(
        ((row.score or Decimal("0")) for row in eligible), default=Decimal("0")
    )
    progress.first_passed_at = next(
        (row.completed_at for row in eligible if row.status == SubmissionStatus.PASSED),
        None,
    )

    item = db.get(AssignmentItem, assignment_item_id)
    db.flush()
    refresh_course_problem(
        db, db.get(Assignment, item.assignment_id).course_id, item.problem_id
    )
