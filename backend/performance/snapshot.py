"""Save durable execution state before disposable benchmark data is removed."""

import json

from app.core.db import SessionLocal
from app.models import Submission, SubmissionCaseResult
from sqlalchemy import select, text


def main():
    with SessionLocal() as db:
        if db.scalar(text("SELECT DATABASE()")) != "integration":
            raise RuntimeError("Snapshots require the disposable integration DB")
        submissions = [
            dict(row._mapping)
            for row in db.execute(
                select(
                    Submission.id,
                    Submission.status,
                    Submission.failure_code,
                    Submission.submitted_at,
                    Submission.completed_at,
                )
            )
        ]
        cases = [
            dict(row._mapping)
            for row in db.execute(
                select(
                    SubmissionCaseResult.submission_id,
                    SubmissionCaseResult.test_case_id,
                    SubmissionCaseResult.judge0_status_id,
                    SubmissionCaseResult.infrastructure_error,
                    SubmissionCaseResult.execution_time_ms,
                    SubmissionCaseResult.memory_kb,
                    SubmissionCaseResult.dispatch_started_at,
                    SubmissionCaseResult.dispatch_attempt_count,
                    SubmissionCaseResult.poll_failure_count,
                )
            )
        ]
    print(json.dumps({"submissions": submissions, "cases": cases}, default=str))


if __name__ == "__main__":
    main()
