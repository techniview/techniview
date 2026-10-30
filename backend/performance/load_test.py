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
from pathlib import Path
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


def _seed_load_scenario(
    students: int, cases_per_submission: int, workload: dict | None = None
) -> tuple[int, int, list[str]]:
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
                    case_order=case_order,
                    visibility=TestVisibility.HIDDEN,
                    input=json.dumps(
                        [[case_order, case_order + 1, case_order + 2, case_order + 3]]
                    ),
                    expected_output=json.dumps(2),
                )
                for case_order in range(1, cases_per_submission + 1)
            ],
        )
        if workload is not None:
            problem.title = workload["title"]
            problem.prompt = workload["prompt"]
            problem.difficulty = Difficulty(workload["difficulty"])
            problem.execution_mode = ExecutionMode(workload["execution_mode"])
            problem.function_name = workload["function_name"]
            problem.starter_code = workload["starter_code"]
            problem.canonical_solution = workload["canonical_solution"]
            problem.cpu_time_limit_seconds = Decimal(
                str(workload["cpu_time_limit_seconds"])
            )
            problem.memory_limit_kb = workload["memory_limit_kb"]
            problem.test_cases = [
                ProblemTestCase(
                    case_order=index,
                    visibility=TestVisibility(case["visibility"]),
                    input=case["input"],
                    expected_output=case["expected_output"],
                )
                for index, case in enumerate(workload["test_cases"], 1)
            ]
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
    source_code: str = SOURCE_CODE,
    observations: list[dict] | None = None,
) -> tuple[int | None, float, int | None, str | None]:
    await start_gate.wait()
    started = time.perf_counter()
    try:
        response = await api.post(
            "/api/submissions",
            headers={
                "Idempotency-Key": str(uuid4()),
                "Cookie": f"{settings.SESSION_COOKIE_NAME}={token}",
            },
            json={
                "problem_id": problem_id,
                "assignment_item_id": assignment_item_id,
                "source_code": source_code,
            },
        )
    except httpx.HTTPError as error:
        return None, time.perf_counter() - started, None, str(error)
    accepted_at = time.perf_counter()
    elapsed = accepted_at - started
    if response.status_code != 202:
        return None, elapsed, response.status_code, response.text[:300]
    try:
        submission_id = response.json()["id"]
        print(
            json.dumps(
                {
                    "event": "submission_accepted",
                    "submission_id": submission_id,
                    "acceptance_seconds": elapsed,
                }
            ),
            flush=True,
        )
        deadline = started + _integer_setting(
            "LOAD_COMPLETION_TIMEOUT_SECONDS", 300, 3600
        )
        poll_errors = []
        while True:
            try:
                result = await api.get(
                    f"/api/submissions/{submission_id}",
                    headers={"Cookie": f"{settings.SESSION_COOKIE_NAME}={token}"},
                )
            except httpx.TransportError as error:
                event = {
                    "event": "result_poll_transport_error",
                    "submission_id": submission_id,
                    "elapsed_seconds": time.perf_counter() - started,
                    "error_type": type(error).__name__,
                }
                poll_errors.append(event)
                print(json.dumps(event), flush=True)
                if time.perf_counter() >= deadline:
                    raise TimeoutError(
                        f"Submission {submission_id} API result timed out"
                    ) from error
                await asyncio.sleep(0.2)
                continue
            result.raise_for_status()
            payload = result.json()
            if payload["done"]:
                if observations is not None:
                    observations.append(
                        {
                            "submission_id": submission_id,
                            "acceptance_seconds": elapsed,
                            "accepted_at_monotonic": accepted_at,
                            "request_started_monotonic": started,
                            "api_completion_seconds": time.perf_counter() - started,
                            "result_poll_transport_error_count": len(poll_errors),
                            "result_poll_transport_errors": poll_errors,
                            "server_submitted_at": payload["submitted_at"],
                            "server_completed_at": payload["completed_at"],
                            "status": payload["status"],
                            "passed_count": payload["passed_count"],
                            "test_count": payload["test_count"],
                        }
                    )
                if observations is not None:
                    print(
                        json.dumps(
                            {"event": "submission_completed", **observations[-1]}
                        ),
                        flush=True,
                    )
                break
            if time.perf_counter() >= deadline:
                raise TimeoutError(f"Submission {submission_id} API result timed out")
            await asyncio.sleep(0.2)
        return submission_id, elapsed, response.status_code, None
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
                    "waiting_on_go_judge",
                    "running_on_go_judge",
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
                samples.setdefault("raw_metrics", []).append(
                    {"at": datetime.now(UTC).isoformat(), "payload": response.text}
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


def _read_queue_waits(submission_ids: list[int]) -> list[float]:
    with SessionLocal() as db:
        rows = db.execute(
            select(
                Submission.submitted_at,
                func.min(SubmissionCaseResult.dispatch_started_at),
            )
            .join(
                SubmissionCaseResult,
                SubmissionCaseResult.submission_id == Submission.id,
            )
            .where(Submission.id.in_(submission_ids))
            .group_by(Submission.id, Submission.submitted_at)
        ).all()
    return [
        max(0.0, (dispatch_started_at - submitted_at).total_seconds())
        for submitted_at, dispatch_started_at in rows
        if dispatch_started_at is not None
    ]


def _read_case_cpu_seconds(submission_ids: list[int]) -> list[float]:
    with SessionLocal() as db:
        values = db.scalars(
            select(SubmissionCaseResult.execution_time_ms).where(
                SubmissionCaseResult.submission_id.in_(submission_ids),
                SubmissionCaseResult.execution_time_ms.is_not(None),
            )
        ).all()
    return [float(value) / 1000 for value in values if value is not None]


async def _run_burst(
    students: int,
    concurrency: int,
    cases_per_submission: int,
    completion_timeout: int,
    problem_id: int,
    assignment_item_id: int,
    tokens: list[str],
    source_code: str = SOURCE_CODE,
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
        "case_waiting_on_go_judge": 0.0,
        "case_running_on_go_judge": 0.0,
        "metrics_scrape_errors": 0.0,
        "metrics_last_scrape_error": "",
    }
    monitor_task = asyncio.create_task(_monitor_metrics(stop_metrics, samples))

    observations: list[dict] = []
    try:
        async with httpx.AsyncClient(
            base_url="http://backend:8000", limits=limits, timeout=timeout
        ) as api:
            start_gate = asyncio.Event()
            tasks = [
                asyncio.create_task(
                    _submit_once(
                        api,
                        token,
                        problem_id,
                        assignment_item_id,
                        start_gate,
                        source_code,
                        observations,
                    )
                )
                for token in tokens
            ]
            await asyncio.sleep(0)
            burst_started = time.perf_counter()
            start_gate.set()
            async with asyncio.timeout(completion_timeout):
                request_results = await asyncio.gather(*tasks, return_exceptions=True)
            api_completion_batch = time.perf_counter() - burst_started
            acceptance_burst = (
                max(r["accepted_at_monotonic"] for r in observations) - burst_started
                if observations
                else api_completion_batch
            )

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
            await asyncio.sleep(0.2)
    finally:
        stop_metrics.set()
        await monitor_task

    configured_go_judge_slots = _integer_setting("LOAD_GO_JUDGE_SLOTS", 4, 100)
    configured_app_workers = _integer_setting("LOAD_APP_WORKERS", 4, 100)

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
    expected_cases = students * cases_per_submission
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

    if any(
        row["status"] != "passed"
        or row["test_count"] != cases_per_submission
        or row["passed_count"] != cases_per_submission
        for row in observations
    ):
        raise AssertionError("API results do not match the selected workload")
    acceptance_latencies = [latency for _submission_id, latency in accepted]
    completion_latencies = [duration for _status, duration in completed.values()]
    api_latencies = [row["api_completion_seconds"] for row in observations]
    queue_waits = _read_queue_waits(submission_ids)
    case_cpu_seconds = _read_case_cpu_seconds(submission_ids)
    failed_cases = actual_cases - passed_cases
    return {
        "raw_samples": observations,
        "result_poll_transport_errors": sum(
            sample["result_poll_transport_error_count"] for sample in observations
        ),
        "submissions_with_result_poll_transport_errors": sum(
            sample["result_poll_transport_error_count"] > 0 for sample in observations
        ),
        "raw_metrics": samples.get("raw_metrics", []),
        "result_poll_interval_seconds": 0.2,
        "api_submission_to_result_seconds": {
            "count": len(api_latencies),
            "p50": statistics.median(api_latencies),
            "p95": _percentile(api_latencies, 0.95),
            "p99": _percentile(api_latencies, 0.99),
            "max": max(api_latencies),
        },
        "api_completion_batch_seconds": api_completion_batch,
        "students": students,
        "submission_concurrency": concurrency,
        "application_worker_replicas_configured": configured_app_workers,
        "go_judge_execution_slots_configured": configured_go_judge_slots,
        "test_cases_per_submission": cases_per_submission,
        "accepted_submissions": len(accepted),
        "acceptance_burst_seconds": round(acceptance_burst, 3),
        "accepted_submissions_per_second": round(students / acceptance_burst, 3),
        "acceptance_latency_seconds": {
            "count": len(acceptance_latencies),
            "p50": round(statistics.median(acceptance_latencies), 3),
            "p95": round(_percentile(acceptance_latencies, 0.95), 3),
            "p99": round(_percentile(acceptance_latencies, 0.99), 3),
            "max": round(max(acceptance_latencies), 3),
        },
        "completion_batch_seconds": round(completion_batch, 3),
        "completed_submissions_per_second": round(students / completion_batch, 3),
        "submission_to_completion_seconds": {
            "count": len(completion_latencies),
            "p50": round(statistics.median(completion_latencies), 3),
            "p95": round(_percentile(completion_latencies, 0.95), 3),
            "p99": round(_percentile(completion_latencies, 0.99), 3),
            "max": round(max(completion_latencies), 3),
        },
        "queue_wait_seconds": {
            "count": len(queue_waits),
            "p50": round(statistics.median(queue_waits), 3),
            "p95": round(_percentile(queue_waits, 0.95), 3),
            "max": round(max(queue_waits), 3),
        },
        "case_cpu_seconds": {
            "count": len(case_cpu_seconds),
            "p50": round(statistics.median(case_cpu_seconds), 3),
            "p95": round(_percentile(case_cpu_seconds, 0.95), 3),
            "max": round(max(case_cpu_seconds), 3),
        },
        "max_observed_submission_queue_depth": int(samples["queue_depth"]),
        "max_observed_oldest_queue_age_seconds": round(samples["queue_age"], 3),
        "max_observed_waiting_to_dispatch_cases": int(
            samples["case_waiting_to_dispatch"]
        ),
        "max_observed_waiting_on_go_judge_cases": int(
            samples["case_waiting_on_go_judge"]
        ),
        "max_observed_running_on_go_judge_cases": int(
            samples["case_running_on_go_judge"]
        ),
        "metrics_scrape_errors": int(samples["metrics_scrape_errors"]),
        "metrics_last_scrape_error": samples["metrics_last_scrape_error"],
        "execution_cases": actual_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "failed_submissions": len(failed_submissions),
    }


def main() -> None:
    students = _integer_setting("LOAD_STUDENTS", 100, 1000)
    concurrency = _integer_setting("LOAD_CONCURRENCY", students, students)
    workload_name = os.getenv("LOAD_WORKLOAD")
    workload = None
    if workload_name:
        catalog = json.loads((Path(__file__).parent / "workloads/v1.json").read_text())
        try:
            workload = catalog["workloads"][workload_name]
        except KeyError as error:
            raise ValueError(f"Unknown versioned workload {workload_name!r}") from error
    cases_per_submission = (
        len(workload["test_cases"])
        if workload
        else _integer_setting("LOAD_CASES_PER_SUBMISSION", 1, 10000)
    )
    completion_timeout = _integer_setting("LOAD_COMPLETION_TIMEOUT_SECONDS", 300, 3600)
    problem_id, assignment_item_id, tokens = _seed_load_scenario(
        students, cases_per_submission, workload
    )
    report = asyncio.run(
        _run_burst(
            students,
            concurrency,
            cases_per_submission,
            completion_timeout,
            problem_id,
            assignment_item_id,
            tokens,
            workload["canonical_solution"] if workload else SOURCE_CODE,
        )
    )
    report["execution_path"] = "go-judge"
    report["workload"] = workload_name or "synthetic-count-evens"
    report["workload_version"] = 1 if workload_name else None
    report["workload_definition"] = workload
    report["source_commit"] = os.getenv("LOAD_SOURCE_COMMIT", "unrecorded")
    report["backend_image_id"] = os.getenv("LOAD_BACKEND_IMAGE_ID", "unrecorded")
    report["worker_image_id"] = os.getenv("LOAD_WORKER_IMAGE_ID", "unrecorded")
    report["runner_image_id"] = os.getenv("LOAD_RUNNER_IMAGE_ID", "unrecorded")
    report["application_image_revision"] = os.getenv(
        "LOAD_APPLICATION_IMAGE_REVISION", "unrecorded"
    )
    report["case_cpu_time_limit_seconds"] = (
        workload["cpu_time_limit_seconds"] if workload else 2.0
    )
    report["case_cpu_time_limit_fraction_p95"] = (
        report["case_cpu_seconds"]["p95"] / report["case_cpu_time_limit_seconds"]
    )
    report["host_profile"] = json.loads(os.getenv("LOAD_HOST_PROFILE_JSON", "{}"))
    report["worker_settings"] = {
        "application_replicas": _integer_setting("LOAD_APP_WORKERS", 4, 100),
        "direct_worker_processes": _integer_setting("DIRECT_WORKER_PROCESSES", 4, 100),
        "go_judge_parallelism": _integer_setting("LOAD_GO_JUDGE_SLOTS", 4, 100),
        "runner_cpu_limit": os.getenv("LOAD_RUNNER_CPU_LIMIT", "unrecorded"),
        "runner_memory_limit": os.getenv("LOAD_RUNNER_MEMORY_LIMIT", "unrecorded"),
        "go_judge_wall_seconds": int(os.getenv("GO_JUDGE_WALL_SECONDS", "5")),
    }
    report["database_pool_settings"] = {
        "api_pool_size": os.getenv("LOAD_API_DB_POOL_SIZE", "unrecorded"),
        "worker_pool_size": os.getenv("LOAD_WORKER_DB_POOL_SIZE", "unrecorded"),
        "max_overflow": os.getenv("LOAD_DB_MAX_OVERFLOW", "unrecorded"),
    }
    report["report_run"] = os.getenv("LOAD_REPORT_RUN", "measured")
    output = os.getenv("LOAD_REPORT_PATH")
    if output:
        Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
