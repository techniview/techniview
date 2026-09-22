from dataclasses import dataclass
from datetime import datetime
from statistics import median

from ..schemas.contracts import AnalyticsMetrics, ErrorCounts


@dataclass(frozen=True)
class MetricRecord:
    first_opened_at: datetime | None = None
    first_passed_at: datetime | None = None
    valid_attempt_count: int = 0
    retry_count: int = 0
    wrong_answer_count: int = 0
    compile_error_count: int = 0
    runtime_error_count: int = 0
    timeout_count: int = 0
    resource_limit_count: int = 0


def record_from_progress(progress: object | None) -> MetricRecord:
    if progress is None:
        return MetricRecord()
    return MetricRecord(
        first_opened_at=progress.first_opened_at,
        first_passed_at=progress.first_passed_at,
        valid_attempt_count=progress.valid_attempt_count,
        retry_count=progress.retry_count,
        wrong_answer_count=progress.wrong_answer_count,
        compile_error_count=progress.compile_error_count,
        runtime_error_count=progress.runtime_error_count,
        timeout_count=progress.timeout_count,
        resource_limit_count=progress.resource_limit_count,
    )


def calculate_metrics(records: list[MetricRecord]) -> AnalyticsMetrics:
    completion_times = [
        (record.first_passed_at - record.first_opened_at).total_seconds()
        for record in records
        if record.first_opened_at is not None and record.first_passed_at is not None
    ]
    assigned_count = len(records)
    completed_count = len(completion_times)
    retries = sum(record.retry_count for record in records)
    return AnalyticsMetrics(
        assigned_count=assigned_count,
        started_count=sum(record.first_opened_at is not None for record in records),
        completed_count=completed_count,
        completion_rate=(completed_count / assigned_count if assigned_count else None),
        avg_completion_seconds=(
            sum(completion_times) / completed_count if completed_count else None
        ),
        median_completion_seconds=(
            median(completion_times) if completion_times else None
        ),
        total_valid_attempts=sum(record.valid_attempt_count for record in records),
        total_retries=retries,
        avg_retries_per_student=(retries / assigned_count if assigned_count else None),
        errors=ErrorCounts(
            wrong_answer=sum(record.wrong_answer_count for record in records),
            compile_error=sum(record.compile_error_count for record in records),
            runtime_error=sum(record.runtime_error_count for record in records),
            timeout=sum(record.timeout_count for record in records),
            resource_limit=sum(record.resource_limit_count for record in records),
        ),
    )
