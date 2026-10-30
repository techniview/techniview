from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import Integer, case, cast, func, select

from ..core.db import SessionLocal
from ..core.observability import http_metrics
from ..models import Submission, SubmissionCaseResult, SubmissionStatus

router = APIRouter(tags=["operations"])


def _count_matching(condition):
    return func.sum(cast(condition, Integer))


def _metric_labels(**values: str) -> str:
    labels = []
    for name, value in values.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        labels.append(f'{name}="{escaped}"')
    return "{" + ",".join(labels) + "}"


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
                ).label("sending_to_go_judge"),
                _count_matching(
                    (SubmissionCaseResult.judge0_token.is_not(None))
                    & (
                        (SubmissionCaseResult.judge0_status_id.is_(None))
                        | (SubmissionCaseResult.judge0_status_id == 1)
                    )
                ).label("waiting_on_go_judge"),
                _count_matching(SubmissionCaseResult.judge0_status_id == 2).label(
                    "running_on_go_judge"
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
            "sending_to_go_judge",
            "waiting_on_go_judge",
            "running_on_go_judge",
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

        completion_cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            minutes=5
        )
        completions = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.completed_at >= completion_cutoff)
        )
        lines.extend(
            [
                "# HELP techniview_submission_completion_rate_per_minute "
                "Completions per minute averaged over the last five minutes.",
                "# TYPE techniview_submission_completion_rate_per_minute gauge",
                "techniview_submission_completion_rate_per_minute "
                f"{(completions or 0) / 5:.3f}",
            ]
        )

        runner_counts = db.execute(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                SubmissionCaseResult.dispatch_attempt_count > 0,
                                SubmissionCaseResult.dispatch_attempt_count - 1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("dispatch_retries"),
                func.coalesce(
                    func.sum(SubmissionCaseResult.poll_failure_count), 0
                ).label("poll_failures"),
            )
        ).one()
        busy_count = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.failure_code == "runner_busy")
        )
        unknown_count = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.failure_code == "runner_outcome_unknown")
        )
        lines.extend(
            [
                "# HELP techniview_runner_dispatch_retries Persisted dispatch retries.",
                "# TYPE techniview_runner_dispatch_retries gauge",
                f"techniview_runner_dispatch_retries {runner_counts.dispatch_retries}",
                "# HELP techniview_runner_poll_failures "
                "Consecutive poll failures in the database.",
                "# TYPE techniview_runner_poll_failures gauge",
                f"techniview_runner_poll_failures {runner_counts.poll_failures}",
                "# HELP techniview_runner_busy_submissions "
                "Runs ended after runner overload.",
                "# TYPE techniview_runner_busy_submissions gauge",
                f"techniview_runner_busy_submissions {busy_count or 0}",
                "# HELP techniview_runner_unknown_outcomes "
                "Runs with unconfirmed dispatch outcomes.",
                "# TYPE techniview_runner_unknown_outcomes gauge",
                f"techniview_runner_unknown_outcomes {unknown_count or 0}",
            ]
        )
    return PlainTextResponse(
        "\n".join(lines) + "\n", media_type="text/plain; version=0.0.4"
    )
