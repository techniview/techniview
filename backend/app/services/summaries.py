from collections import Counter
from decimal import Decimal

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    Course,
    CourseMembership,
    CourseProblemAnalytics,
    CourseProblemErrorCount,
    StudentAssignmentProgress,
    Submission,
    SubmissionStatus,
)
from .progress import ERROR_COUNTER_FIELDS


def refresh_course_problem(db: Session, course_id: int, problem_id: int) -> None:
    """Refresh within the caller's transaction; serialize writers on the course."""
    db.scalar(select(Course.id).where(Course.id == course_id).with_for_update())
    rows = db.scalars(
        select(StudentAssignmentProgress)
        .select_from(AssignmentItem)
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(AssignmentRecipient, AssignmentRecipient.assignment_id == Assignment.id)
        .join(
            CourseMembership, CourseMembership.id == AssignmentRecipient.membership_id
        )
        .outerjoin(
            StudentAssignmentProgress,
            and_(
                StudentAssignmentProgress.assignment_item_id == AssignmentItem.id,
                StudentAssignmentProgress.student_id == CourseMembership.user_id,
            ),
        )
        .where(
            Assignment.course_id == course_id,
            AssignmentItem.problem_id == problem_id,
            Assignment.state != AssignmentState.DRAFT,
            AssignmentRecipient.removed_at.is_(None),
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    ).all()
    summary = db.scalar(
        select(CourseProblemAnalytics)
        .where(
            CourseProblemAnalytics.course_id == course_id,
            CourseProblemAnalytics.problem_id == problem_id,
        )
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if summary is None:
        summary = CourseProblemAnalytics(course_id=course_id, problem_id=problem_id)
        db.add(summary)
    summary.assigned_count = len(rows)
    progress = [row for row in rows if row is not None]
    summary.started_count = sum(row.first_opened_at is not None for row in progress)
    completed = [row for row in progress if row.first_passed_at is not None]
    summary.completed_count = len(completed)
    summary.completion_seconds_sum = sum(
        (
            Decimal(str((row.first_passed_at - row.first_opened_at).total_seconds()))
            for row in completed
            if row.first_opened_at is not None
        ),
        Decimal("0"),
    )
    for field in ("valid_attempt_count", "retry_count", *ERROR_COUNTER_FIELDS.values()):
        setattr(summary, field, sum(getattr(row, field) for row in progress))
    db.execute(
        delete(CourseProblemErrorCount).where(
            CourseProblemErrorCount.course_id == course_id,
            CourseProblemErrorCount.problem_id == problem_id,
        )
    )
    errors = db.scalars(
        select(Submission.python_exception_type)
        .join(AssignmentItem, AssignmentItem.id == Submission.assignment_item_id)
        .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
        .join(AssignmentRecipient, AssignmentRecipient.assignment_id == Assignment.id)
        .join(
            CourseMembership,
            CourseMembership.id == AssignmentRecipient.membership_id,
        )
        .where(
            Assignment.course_id == course_id,
            CourseMembership.user_id == Submission.student_id,
            AssignmentRecipient.removed_at.is_(None),
            Submission.problem_id == problem_id,
            Assignment.state != AssignmentState.DRAFT,
            Submission.completed_at.is_not(None),
            Submission.status.not_in(
                (
                    SubmissionStatus.QUEUED,
                    SubmissionStatus.RUNNING,
                    SubmissionStatus.INFRASTRUCTURE_ERROR,
                )
            ),
            Submission.python_exception_type.is_not(None),
        )
        .with_for_update()
    )
    for exception, count in Counter(errors).items():
        db.add(
            CourseProblemErrorCount(
                course_id=course_id,
                problem_id=problem_id,
                python_exception_type=exception,
                error_count=count,
            )
        )
    db.flush()


def rebuild_course_summaries(db: Session) -> None:
    db.execute(delete(CourseProblemErrorCount))
    db.execute(delete(CourseProblemAnalytics))
    contexts = db.execute(
        select(Assignment.course_id, AssignmentItem.problem_id)
        .join(AssignmentItem, AssignmentItem.assignment_id == Assignment.id)
        .where(Assignment.state != AssignmentState.DRAFT)
        .distinct()
    ).all()
    for course_id, problem_id in contexts:
        refresh_course_problem(db, course_id, problem_id)


def summary_metrics(summaries, median_completion_seconds):
    from ..schemas.contracts import AnalyticsMetrics, ErrorCounts

    assigned = sum(row.assigned_count for row in summaries)
    started = sum(row.started_count for row in summaries)
    completed = sum(row.completed_count for row in summaries)
    retries = sum(row.retry_count for row in summaries)
    seconds = sum(row.completion_seconds_sum for row in summaries)
    return AnalyticsMetrics(
        assigned_count=assigned,
        started_count=started,
        completed_count=completed,
        completion_rate=completed / assigned if assigned else None,
        avg_completion_seconds=float(seconds / completed) if completed else None,
        median_completion_seconds=median_completion_seconds,
        total_valid_attempts=sum(row.valid_attempt_count for row in summaries),
        total_retries=retries,
        avg_retries_per_student=retries / started if started else None,
        errors=ErrorCounts(
            **{
                name: sum(getattr(row, field) for row in summaries)
                for name, field in (
                    ("wrong_answer", "wrong_answer_count"),
                    ("compile_error", "compile_error_count"),
                    ("runtime_error", "runtime_error_count"),
                    ("timeout", "timeout_count"),
                    ("resource_limit", "resource_limit_count"),
                )
            }
        ),
    )
