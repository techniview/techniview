"""Rebuild derived progress during a maintenance window with all writers stopped."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, noload

from ..core.db import SessionLocal
from ..models import (
    StudentAssignmentProgress,
    StudentPracticeProgress,
    Submission,
    SubmissionStatus,
)
from .progress import ERROR_COUNTER_FIELDS, finalize_progress
from .summaries import rebuild_course_summaries


def rebuild_progress(db: Session) -> int:
    for model in (StudentPracticeProgress, StudentAssignmentProgress):
        for progress in db.scalars(select(model)):
            progress.first_passed_at = None
            progress.last_attempt_at = None
            progress.best_score = Decimal("0")
            for field in (
                "valid_attempt_count",
                "retry_count",
                *ERROR_COUNTER_FIELDS.values(),
            ):
                setattr(progress, field, 0)
    submissions = db.scalars(
        select(Submission)
        .options(noload(Submission.case_results))
        .order_by(Submission.completed_at, Submission.submitted_at, Submission.id)
    ).all()
    for submission in submissions:
        if submission.assignment_item_id is None:
            model = StudentPracticeProgress
            key = (submission.student_id, submission.problem_id)
            values = {"problem_id": submission.problem_id}
        else:
            model = StudentAssignmentProgress
            key = (submission.student_id, submission.assignment_item_id)
            values = {"assignment_item_id": submission.assignment_item_id}
        progress = db.get(model, key)
        if progress is None:
            progress = model(student_id=submission.student_id, **values)
            db.add(progress)
        if (
            progress.first_opened_at is None
            or submission.submitted_at < progress.first_opened_at
        ):
            progress.first_opened_at = submission.submitted_at
        db.flush()
        if submission.completed_at is not None and submission.status not in (
            SubmissionStatus.QUEUED,
            SubmissionStatus.RUNNING,
            SubmissionStatus.INFRASTRUCTURE_ERROR,
        ):
            finalize_progress(db, submission)
    db.flush()
    rebuild_course_summaries(db)
    return len(submissions)


def main() -> None:
    with SessionLocal.begin() as db:
        count = rebuild_progress(db)
    print(f"Rebuilt progress from {count} submissions.")


if __name__ == "__main__":
    main()
