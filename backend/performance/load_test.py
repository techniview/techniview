"""Run a configurable submission burst against the disposable integration stack."""

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from uuid import uuid4

import httpx
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import create_session, hash_password
from app.models import Problem, Submission, SubmissionCaseResult, User, UserRole
from sqlalchemy import func, select, text


def _integer_setting(name: str, default: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(percentile * len(ordered)) - 1)]


def _metric_value(payload: str, metric_name: str) -> float:
    for line in payload.splitlines():
        if line.startswith(f"{metric_name} "):
            return float(line.split(maxsplit=1)[1])
    raise AssertionError(f"Missing metric: {metric_name}")


def main() -> None:
    students = _integer_setting("LOAD_STUDENTS", 50, 500)
    concurrency = _integer_setting("LOAD_CONCURRENCY", students, students)
    completion_timeout = _integer_setting("LOAD_COMPLETION_TIMEOUT_SECONDS", 180, 1800)
    batch = uuid4().hex

    with SessionLocal() as db:
        if db.scalar(text("SELECT DATABASE()")) != "integration":
            raise RuntimeError(
                "Load tests must run against the disposable integration DB"
            )
        problem = db.scalar(select(Problem).where(Problem.title == "Count Evens"))
        if problem is None:
            raise RuntimeError("The seeded Count Evens problem was not found")
        case_count = len(problem.test_cases)
        users = [
            User(
                name=f"Load student {index}",
                email=f"load-{batch}-{index}@example.test",
                password_hash=hash_password("load-test-only-password"),
                role=UserRole.STUDENT,
            )
            for index in range(students)
        ]
        db.add_all(users)
        db.commit()
        credentials = [create_session(db, user)[0] for user in users]

    def submit(token: str) -> tuple[int, float]:
        started = time.perf_counter()
        with httpx.Client(
            base_url="http://backend:8000",
            timeout=30,
            cookies={settings.SESSION_COOKIE_NAME: token},
        ) as api:
            response = api.post(
                "/api/submissions",
                json={
                    "problem_id": problem.id,
                    "source_code": (
                        "def count_evens(values):\n"
                        "    return sum(x % 2 == 0 for x in values)"
                    ),
                },
            )
        if response.status_code != 202:
            raise AssertionError(
                f"Submission rejected: {response.status_code} {response.text}"
            )
        return response.json()["id"], time.perf_counter() - started

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        accepted = list(executor.map(submit, credentials))
    accepted_elapsed = time.perf_counter() - started
    submission_ids = [submission_id for submission_id, _ in accepted]
    acceptance_latencies = [latency for _, latency in accepted]

    queue_depth_max = 0.0
    queue_age_max = 0.0
    deadline = time.monotonic() + completion_timeout
    completed: dict[int, tuple[str, float]] = {}
    with httpx.Client(base_url="http://backend:8000", timeout=10) as metrics_client:
        while len(completed) < students:
            response = metrics_client.get("/api/metrics")
            response.raise_for_status()
            queue_depth_max = max(
                queue_depth_max,
                _metric_value(response.text, "techniview_submission_queue_depth"),
            )
            queue_age_max = max(
                queue_age_max,
                _metric_value(
                    response.text, "techniview_submission_queue_oldest_seconds"
                ),
            )
            with SessionLocal() as db:
                rows = db.execute(
                    select(
                        Submission.id,
                        Submission.status,
                        Submission.submitted_at,
                        Submission.completed_at,
                    ).where(Submission.id.in_(submission_ids))
                )
                for row in rows:
                    if row.completed_at is not None:
                        completed[row.id] = (
                            row.status.value,
                            (row.completed_at - row.submitted_at).total_seconds(),
                        )
            if len(completed) == students:
                break
            if time.monotonic() >= deadline:
                unfinished = students - len(completed)
                raise TimeoutError(
                    f"{unfinished} of {students} submissions did not finish "
                    f"within {completion_timeout} seconds"
                )
            time.sleep(0.1)

    batch_completion = time.perf_counter() - started
    failed = {
        submission_id: status
        for submission_id, (status, _) in completed.items()
        if status != "passed"
    }
    if failed:
        raise AssertionError(f"Submissions did not pass: {failed}")
    with SessionLocal() as db:
        actual_cases = db.scalar(
            select(func.count())
            .select_from(SubmissionCaseResult)
            .where(SubmissionCaseResult.submission_id.in_(submission_ids))
        )
    if actual_cases != students * case_count:
        raise AssertionError(
            f"Expected {students * case_count} execution cases, found {actual_cases}"
        )

    end_to_end = [duration for _, duration in completed.values()]
    print(
        json.dumps(
            {
                "students": students,
                "submission_concurrency": concurrency,
                "accepted_submissions": len(accepted),
                "acceptance_burst_seconds": round(accepted_elapsed, 3),
                "acceptance_latency_seconds": {
                    "p50": round(statistics.median(acceptance_latencies), 3),
                    "p95": round(_percentile(acceptance_latencies, 0.95), 3),
                    "max": round(max(acceptance_latencies), 3),
                },
                "completion_batch_seconds": round(batch_completion, 3),
                "submission_to_completion_seconds": {
                    "p50": round(statistics.median(end_to_end), 3),
                    "p95": round(_percentile(end_to_end, 0.95), 3),
                    "max": round(max(end_to_end), 3),
                },
                "max_observed_queue_depth": int(queue_depth_max),
                "max_observed_oldest_queue_age_seconds": round(queue_age_max, 3),
                "execution_cases": actual_cases,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
