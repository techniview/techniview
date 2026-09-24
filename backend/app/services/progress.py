from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    ErrorCategory,
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
            CourseMembership.withdrawn_at.is_(None),
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
    now = utc_now()
    if assignment_item_id is not None:
        require_assigned_item(db, student_id, problem_id, assignment_item_id)
        progress = _locked_assignment_progress(
            db,
            student_id,
            assignment_item_id,
        )
        if progress is None:
            progress = StudentAssignmentProgress(
                student_id=student_id,
                assignment_item_id=assignment_item_id,
                first_opened_at=now,
            )
            db.add(progress)
        elif progress.first_opened_at is None:
            progress.first_opened_at = now
        return progress

    db.scalar(select(User.id).where(User.id == student_id).with_for_update())
    progress = _locked_practice_progress(db, student_id, problem_id)
    if progress is None:
        progress = StudentPracticeProgress(
            student_id=student_id,
            problem_id=problem_id,
            first_opened_at=now,
        )
        db.add(progress)
    elif progress.first_opened_at is None:
        progress.first_opened_at = now
    return progress


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


def recompute_assignment_grade(
    db: Session, student_id: int, assignment_item_id: int
) -> None:
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
