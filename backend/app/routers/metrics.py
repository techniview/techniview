from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import Integer, cast, func, select

from ..core.db import SessionLocal
from ..core.observability import http_metrics
from ..models import Submission, SubmissionCaseResult, SubmissionStatus

router = APIRouter(tags=["operations"])


def _count_matching(condition):
    return func.sum(cast(condition, Integer))


@router.get("/metrics", include_in_schema=False)
def metrics():
    lines = [http_metrics.render().rstrip()]
    with SessionLocal() as db:
        submission_counts = db.execute(
            select(
                Submission.status, Submission.is_practice_run, func.count()
            ).group_by(Submission.status, Submission.is_practice_run)
        )
        lines.extend(
            [
                "# HELP techniview_submissions Submissions by status and run type.",
                "# TYPE techniview_submissions gauge",
            ]
        )
        for status, is_practice_run, count in submission_counts:
            lines.append(
                "techniview_submissions"
                "{"
                f'status="{status.value}",'
                f'practice_run="{str(is_practice_run).lower()}"'
                f"}} {count}"
            )

        case_counts = db.execute(
            select(
                func.count().label("total"),
                _count_matching(
                    (SubmissionCaseResult.judge0_token.is_(None))
                    & (SubmissionCaseResult.judge0_status_id.is_(None))
                    & (SubmissionCaseResult.dispatch_started_at.is_(None))
                ).label("waiting_to_dispatch"),
                _count_matching(
                    (SubmissionCaseResult.judge0_token.is_(None))
                    & (SubmissionCaseResult.judge0_status_id.is_(None))
                    & (SubmissionCaseResult.dispatch_started_at.is_not(None))
                ).label("sending_to_judge0"),
                _count_matching(
                    (SubmissionCaseResult.judge0_token.is_not(None))
                    & (
                        (SubmissionCaseResult.judge0_status_id.is_(None))
                        | (SubmissionCaseResult.judge0_status_id == 1)
                    )
                ).label("waiting_on_judge0"),
                _count_matching(SubmissionCaseResult.judge0_status_id == 2).label(
                    "running_on_judge0"
                ),
                _count_matching(SubmissionCaseResult.infrastructure_error).label(
                    "infrastructure_errors"
                ),
            )
            .join(Submission, Submission.id == SubmissionCaseResult.submission_id)
            .where(
                Submission.status.in_(
                    (SubmissionStatus.QUEUED, SubmissionStatus.RUNNING)
                )
            )
        ).one()
        lines.extend(
            [
                "# HELP techniview_execution_cases Current execution cases by phase.",
                "# TYPE techniview_execution_cases gauge",
            ]
        )
        for phase in (
            "total",
            "waiting_to_dispatch",
            "sending_to_judge0",
            "waiting_on_judge0",
            "running_on_judge0",
            "infrastructure_errors",
        ):
            lines.append(
                f'techniview_execution_cases{{phase="{phase}"}} '
                f"{getattr(case_counts, phase) or 0}"
            )

        queue = db.execute(
            select(
                func.count().label("count"),
                func.min(Submission.submitted_at).label("oldest"),
            ).where(Submission.status == SubmissionStatus.QUEUED)
        ).one()
        oldest_age = (
            max(
                0.0,
                (datetime.now(UTC).replace(tzinfo=None) - queue.oldest).total_seconds(),
            )
            if queue.oldest
            else 0.0
        )
        lines.extend(
            [
                "# HELP techniview_submission_queue_depth Queued submissions.",
                "# TYPE techniview_submission_queue_depth gauge",
                f"techniview_submission_queue_depth {queue.count}",
                "# HELP techniview_submission_queue_oldest_seconds Oldest queue age.",
                "# TYPE techniview_submission_queue_oldest_seconds gauge",
                f"techniview_submission_queue_oldest_seconds {oldest_age:.3f}",
            ]
        )
    return PlainTextResponse(
        "\n".join(lines) + "\n", media_type="text/plain; version=0.0.4"
    )
