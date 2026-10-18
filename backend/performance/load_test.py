"""Run a real, synchronized assignment submission burst on the integration stack."""

import asyncio
import json
import os
import secrets
import statistics
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import ceil
from uuid import uuid4

import httpx
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_token
from app.models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    Course,
    CourseMembership,
    Difficulty,
    ExecutionMode,
    MembershipRole,
    Problem,
    ProblemOrigin,
    ProblemState,
    ProblemTestCase,
    Submission,
    SubmissionCaseResult,
    TestVisibility,
    User,
    UserRole,
    UserSession,
)
from sqlalchemy import func, select, text

CASE_COUNT = 1
SOURCE_CODE = "def count_evens(values):\n    return sum(x % 2 == 0 for x in values)"


def _integer_setting(name: str, default: int, maximum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, ceil(percentile * len(ordered)) - 1)]


def _metric_value(payload: str, metric_name: str, labels: str = "") -> float:
    prefix = f"{metric_name}{labels} "
    for line in payload.splitlines():
        if line.startswith(prefix):
            return float(line.removeprefix(prefix))
    raise AssertionError(f"Missing metric: {prefix.strip()}")


def _seed_load_scenario(students: int) -> tuple[int, int, list[str]]:
    batch = uuid4().hex
    now = datetime.now(UTC).replace(tzinfo=None)
    available_at = now - timedelta(minutes=1)
    due_at = now + timedelta(days=1)
    tokens = [secrets.token_urlsafe(32) for _ in range(students)]

    with SessionLocal() as db:
        if db.scalar(text("SELECT DATABASE()")) != "integration":
            raise RuntimeError(
                "Load tests must run against the disposable integration DB"
            )

        instructor = User(
            name=f"Load instructor {batch}",
            email=f"load-instructor-{batch}@example.test",
            password_hash="unused-load-test-password",
            role=UserRole.PROFESSOR,
        )
        users = [
            User(
                name=f"Load student {index}",
                email=f"load-{batch}-{index}@example.test",
                password_hash="unused-load-test-password",
                role=UserRole.STUDENT,
            )
            for index in range(students)
        ]
        db.add_all([instructor, *users])
        db.flush()

        course = Course(name=f"Load course {batch}", timezone="UTC")
        db.add(course)
        db.flush()
        instructor_membership = CourseMembership(
            course_id=course.id,
            user_id=instructor.id,
            role=MembershipRole.INSTRUCTOR,
        )
        memberships = [
            CourseMembership(
                course_id=course.id,
                user_id=user.id,
                role=MembershipRole.STUDENT,
            )
            for user in users
        ]
        db.add_all([instructor_membership, *memberships])
        db.flush()

        problem = Problem(
            origin=ProblemOrigin.IMPORTED,
            state=ProblemState.PUBLISHED,
            title=f"Load Count Evens {batch}",
            prompt="Return the number of even integers in the input list.",
            difficulty=Difficulty.EASY,
            execution_mode=ExecutionMode.CALL_BASED,
            function_name="count_evens",
            starter_code="def count_evens(values):\n    pass",
            canonical_solution=SOURCE_CODE,
            cpu_time_limit_seconds=Decimal("2.000"),
            memory_limit_kb=128000,
            test_cases=[
                ProblemTestCase(
                    case_order=1,
                    visibility=TestVisibility.HIDDEN,
                    input=json.dumps([[1, 2, 3, 4]]),
                    expected_output=json.dumps(2),
                )
            ],
        )
        db.add(problem)
        db.flush()

        assignment = Assignment(
            course_id=course.id,
            assigned_by_membership_id=instructor_membership.id,
            title=f"Concurrent load assignment {batch}",
            state=AssignmentState.PUBLISHED,
            available_at=available_at,
            due_at=due_at,
            recipient_mode="all",
            selected_membership_ids=[],
        )
        db.add(assignment)
        db.flush()
        item = AssignmentItem(
            assignment_id=assignment.id,
            problem_id=problem.id,
            item_order=1,
            points=Decimal("1.0000"),
        )
        db.add(item)
        db.flush()

        db.add_all(
            [
                AssignmentRecipient(
                    assignment_id=assignment.id,
                    membership_id=membership.id,
                    course_id=course.id,
                )
                for membership in memberships
            ]
        )
        db.add_all(
            [
                UserSession(
                    token_hash=hash_token(token),
                    user_id=user.id,
                    created_at=now,
                    last_used_at=now,
                    expires_at=now + timedelta(days=settings.SESSION_DAYS),
                )
                for token, user in zip(tokens, users, strict=True)
            ]
        )
        db.commit()
        return problem.id, item.id, tokens


async def _submit_once(
    api: httpx.AsyncClient,
    token: str,
    problem_id: int,
    assignment_item_id: int,
    start_gate: asyncio.Event,
) -> tuple[int | None, float, int | None, str | None]:
    await start_gate.wait()
    started = time.perf_counter()
    try:
        response = await api.post(
            "/api/submissions",
            json={
                "problem_id": problem_id,
                "assignment_item_id": assignment_item_id,
                "source_code": SOURCE_CODE,
            },
            cookies={settings.SESSION_COOKIE_NAME: token},
        )
    except httpx.HTTPError as error:
        return None, time.perf_counter() - started, None, str(error)
    elapsed = time.perf_counter() - started
    if response.status_code != 202:
        return None, elapsed, response.status_code, response.text[:300]
    try:
        return response.json()["id"], elapsed, response.status_code, None
    except (KeyError, ValueError) as error:
        return None, elapsed, response.status_code, f"Invalid response: {error}"


async def _monitor_metrics(stop: asyncio.Event, samples: dict[str, float]) -> None:
    async with httpx.AsyncClient(base_url="http://backend:8000", timeout=10) as api:
        while not stop.is_set():
            try:
                response = await api.get("/api/metrics")
                response.raise_for_status()
                samples["queue_depth"] = max(
                    samples["queue_depth"],
                    _metric_value(response.text, "techniview_submission_queue_depth"),
                )
                samples["queue_age"] = max(
                    samples["queue_age"],
                    _metric_value(
                        response.text, "techniview_submission_queue_oldest_seconds"
                    ),
                )
                for phase in (
                    "waiting_to_dispatch",
                    "waiting_on_judge0",
                    "running_on_judge0",
                ):
                    key = f"case_{phase}"
                    samples[key] = max(
                        samples[key],
                        _metric_value(
                            response.text,
                            "techniview_execution_cases",
                            f'{{phase="{phase}"}}',
                        ),
                    )
            except (httpx.HTTPError, AssertionError, ValueError) as error:
                samples["metrics_scrape_errors"] += 1
                samples["metrics_last_scrape_error"] = str(error)[:300]
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass


def _read_completion_rows(
    submission_ids: list[int],
) -> list[tuple[int, str, datetime, datetime | None]]:
    with SessionLocal() as db:
        return list(
            db.execute(
                select(
                    Submission.id,
                    Submission.status,
                    Submission.submitted_at,
                    Submission.completed_at,
                ).where(Submission.id.in_(submission_ids))
            ).all()
        )


async def _run_burst(
    students: int,
    concurrency: int,
    completion_timeout: int,
    problem_id: int,
    assignment_item_id: int,
    tokens: list[str],
) -> dict:
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    timeout = httpx.Timeout(300)
    stop_metrics = asyncio.Event()
    samples = {
        "queue_depth": 0.0,
        "queue_age": 0.0,
        "case_waiting_to_dispatch": 0.0,
        "case_waiting_on_judge0": 0.0,
        "case_running_on_judge0": 0.0,
        "metrics_scrape_errors": 0.0,
        "metrics_last_scrape_error": "",
    }
    monitor_task = asyncio.create_task(_monitor_metrics(stop_metrics, samples))

    try:
        async with httpx.AsyncClient(
            base_url="http://backend:8000", limits=limits, timeout=timeout
        ) as api:
            start_gate = asyncio.Event()
            tasks = [
                asyncio.create_task(
                    _submit_once(api, token, problem_id, assignment_item_id, start_gate)
                )
                for token in tokens
            ]
            await asyncio.sleep(0)
            burst_started = time.perf_counter()
            start_gate.set()
            request_results = await asyncio.gather(*tasks, return_exceptions=True)
            acceptance_burst = time.perf_counter() - burst_started

        errors = [
            f"{type(result).__name__}: {result!r}"
            for result in request_results
            if isinstance(result, BaseException)
        ]
        results = [
            result
            for result in request_results
            if not isinstance(result, BaseException)
        ]
        failed = [
            {
                "status": status,
                "error": error,
                "latency_seconds": round(latency, 3),
            }
            for _submission_id, latency, status, error in results
            if status != 202 or error is not None
        ]
        if errors or failed:
            raise AssertionError(
                f"{len(errors) + len(failed)} of {students} requests failed; "
                f"exceptions={errors[:5]}, responses={failed[:5]}"
            )

        accepted = [
            (submission_id, latency)
            for submission_id, latency, _status, _error in results
            if submission_id is not None
        ]
        if len(accepted) != students:
            raise AssertionError(
                f"Expected {students} accepted submissions, received {len(accepted)}"
            )
        submission_ids = [submission_id for submission_id, _ in accepted]
        if len(set(submission_ids)) != students:
            raise AssertionError("Submission API returned duplicate IDs")

        deadline = time.monotonic() + completion_timeout
        completed: dict[int, tuple[str, float]] = {}
        while len(completed) < students:
            rows = _read_completion_rows(submission_ids)
            for row in rows:
                if row.completed_at is not None:
                    completed[row.id] = (
                        row.status.value,
                        (row.completed_at - row.submitted_at).total_seconds(),
                    )
            if len(completed) == students:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"{students - len(completed)} of {students} submissions did not "
                    f"finish within {completion_timeout} seconds"
                )
            await asyncio.sleep(0.5)
    finally:
        stop_metrics.set()
        await monitor_task

    if samples["metrics_scrape_errors"]:
        raise AssertionError(
            f"Metrics scraping failed {int(samples['metrics_scrape_errors'])} times; "
            f"last error: {samples['metrics_last_scrape_error']}"
        )

    completion_batch = time.perf_counter() - burst_started
    failed_submissions = {
        submission_id: status
        for submission_id, (status, _duration) in completed.items()
        if status != "passed"
    }
    if failed_submissions:
        raise AssertionError(
            f"Submissions did not pass: {dict(list(failed_submissions.items())[:10])}"
        )

    with SessionLocal() as db:
        persisted_submissions = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.id.in_(submission_ids),
                Submission.assignment_item_id == assignment_item_id,
            )
        )
        actual_cases = db.scalar(
            select(func.count())
            .select_from(SubmissionCaseResult)
            .where(SubmissionCaseResult.submission_id.in_(submission_ids))
        )
        passed_cases = db.scalar(
            select(func.count())
            .select_from(SubmissionCaseResult)
            .where(
                SubmissionCaseResult.submission_id.in_(submission_ids),
                SubmissionCaseResult.judge0_status_id == 3,
            )
        )
    expected_cases = students * CASE_COUNT
    if persisted_submissions != students:
        raise AssertionError(
            f"Expected {students} durable assignment submissions, "
            f"found {persisted_submissions}"
        )
    if actual_cases != expected_cases or passed_cases != expected_cases:
        raise AssertionError(
            f"Expected {expected_cases} passed execution cases, found "
            f"{passed_cases} passed of {actual_cases} persisted"
        )

    acceptance_latencies = [latency for _submission_id, latency in accepted]
    completion_latencies = [duration for _status, duration in completed.values()]
    return {
        "students": students,
        "submission_concurrency": concurrency,
        "test_cases_per_submission": CASE_COUNT,
        "accepted_submissions": len(accepted),
        "acceptance_burst_seconds": round(acceptance_burst, 3),
        "accepted_submissions_per_second": round(students / acceptance_burst, 3),
        "acceptance_latency_seconds": {
            "p50": round(statistics.median(acceptance_latencies), 3),
            "p95": round(_percentile(acceptance_latencies, 0.95), 3),
            "p99": round(_percentile(acceptance_latencies, 0.99), 3),
            "max": round(max(acceptance_latencies), 3),
        },
        "completion_batch_seconds": round(completion_batch, 3),
        "completed_submissions_per_second": round(students / completion_batch, 3),
        "submission_to_completion_seconds": {
            "p50": round(statistics.median(completion_latencies), 3),
            "p95": round(_percentile(completion_latencies, 0.95), 3),
            "p99": round(_percentile(completion_latencies, 0.99), 3),
            "max": round(max(completion_latencies), 3),
        },
        "max_observed_submission_queue_depth": int(samples["queue_depth"]),
        "max_observed_oldest_queue_age_seconds": round(samples["queue_age"], 3),
        "max_observed_waiting_to_dispatch_cases": int(
            samples["case_waiting_to_dispatch"]
        ),
        "max_observed_waiting_on_judge0_cases": int(samples["case_waiting_on_judge0"]),
        "max_observed_running_on_judge0_cases": int(samples["case_running_on_judge0"]),
        "metrics_scrape_errors": int(samples["metrics_scrape_errors"]),
        "metrics_last_scrape_error": samples["metrics_last_scrape_error"],
        "execution_cases": actual_cases,
    }


def main() -> None:
    students = _integer_setting("LOAD_STUDENTS", 1000, 1000)
    concurrency = _integer_setting("LOAD_CONCURRENCY", students, students)
    completion_timeout = _integer_setting("LOAD_COMPLETION_TIMEOUT_SECONDS", 1200, 2700)
    problem_id, assignment_item_id, tokens = _seed_load_scenario(students)
    report = asyncio.run(
        _run_burst(
            students,
            concurrency,
            completion_timeout,
            problem_id,
            assignment_item_id,
            tokens,
        )
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
