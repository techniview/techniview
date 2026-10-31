import asyncio
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context

import pytest
from app.core import observability
from app.core.observability import HttpMetrics
from app.models import (
    ProblemTestCase,
    Submission,
    SubmissionStatus,
    User,
)
from app.routers import metrics
from app.routers.submissions import _submission_response
from app.services.execution import snapshot_case_result
from main import RequestObservabilityMiddleware
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def _observe_http_requests(path, count):
    worker_metrics = HttpMetrics(path)
    for _ in range(count):
        worker_metrics.observe("GET", "/api/health/ready", 200, 0.01)
    worker_metrics._write_queue.join()


def _initialize_http_metrics(path, start_gate):
    start_gate.wait()
    HttpMetrics(path)


def _saturate_http_metrics(path):
    HttpMetrics.write_queue_capacity = 1
    worker_metrics = HttpMetrics(path)
    writer_entered = threading.Event()
    release_writer = threading.Event()
    persist = worker_metrics._write_observation

    def hold_first_write(*observation):
        if not writer_entered.is_set():
            writer_entered.set()
            release_writer.wait(timeout=5)
        persist(*observation)

    worker_metrics._write_observation = hold_first_write
    worker_metrics.observe("GET", "/api/health/ready", 200, 0.01)
    assert writer_entered.wait(timeout=5)
    worker_metrics.observe("GET", "/api/health/ready", 200, 0.02)
    worker_metrics.observe("GET", "/api/health/ready", 200, 0.03)
    release_writer.set()
    worker_metrics._write_queue.join()


def samples(payload):
    return {
        key: float(value)
        for line in payload.splitlines()
        if line and not line.startswith("#")
        for key, value in [line.rsplit(" ", 1)]
    }


@pytest.fixture
def metrics_database(db_session, monkeypatch):
    monkeypatch.setattr(
        metrics, "SessionLocal", sessionmaker(bind=db_session.get_bind())
    )
    monkeypatch.setattr(metrics, "http_metrics", HttpMetrics())
    return db_session


def test_execution_metrics_classify_persisted_cases_without_sensitive_data(
    metrics_database,
):
    db = metrics_database
    student = db.scalar(select(User).where(User.email == "student@techniview.local"))
    case = db.scalar(select(ProblemTestCase).order_by(ProblemTestCase.id))
    now = datetime.now(UTC).replace(tzinfo=None)
    states = [
        (None, None, None, False),
        (None, None, now, False),
        ("private-judge-token-1", None, now, False),
        ("private-judge-token-2", 1, now, False),
        ("private-judge-token-3", 2, now, False),
        ("private-judge-token-4", 2, now, False),
        ("private-judge-token-5", 13, now, True),
    ]
    for index, (token, status_id, dispatch, infra_error) in enumerate(states):
        submission = Submission(
            student_id=student.id,
            problem_id=case.problem_id,
            source_code="private-source-code",
            status=SubmissionStatus.QUEUED if index == 0 else SubmissionStatus.RUNNING,
            is_practice_run=index == 0,
            submitted_at=now - timedelta(seconds=120),
        )
        db.add(submission)
        db.flush()
        case_result = snapshot_case_result(
            submission_id=submission.id,
            problem=case.problem,
            case=case,
            source_code=submission.source_code,
            judge0_token=token,
            judge0_status_id=status_id,
            dispatch_started_at=dispatch,
            infrastructure_error=infra_error,
            stdout="private-stdout",
            stderr="private-stderr",
        )
        if index == 2:
            case_result.dispatch_attempt_count = 3
            case_result.poll_failure_count = 2
        db.add(case_result)
    completed = Submission(
        student_id=student.id,
        problem_id=case.problem_id,
        source_code="private-completed-source",
        status=SubmissionStatus.PASSED,
    )
    db.add(completed)
    db.add_all(
        [
            Submission(
                student_id=student.id,
                problem_id=case.problem_id,
                source_code="",
                status=SubmissionStatus.INFRASTRUCTURE_ERROR,
                completed_at=now,
                failure_code="runner_busy",
            ),
            Submission(
                student_id=student.id,
                problem_id=case.problem_id,
                source_code="",
                status=SubmissionStatus.INFRASTRUCTURE_ERROR,
                completed_at=now,
                failure_code="runner_outcome_unknown",
            ),
        ]
    )
    db.flush()
    # A stale case under a finalized submission must not inflate active work.
    db.add(
        snapshot_case_result(
            case.problem, case, completed.source_code, submission_id=completed.id
        )
    )
    db.commit()

    payload = metrics.metrics().body.decode()
    values = samples(payload)
    for phase, count in {
        "total": 7,
        "waiting_to_dispatch": 1,
        "sending_to_go_judge": 1,
        "waiting_on_go_judge": 2,
        "running_on_go_judge": 2,
        "infrastructure_errors": 1,
    }.items():
        assert values[f'techniview_execution_cases{{phase="{phase}"}}'] == count
    assert values['techniview_submissions{status="queued",practice_run="true"}'] == 1
    assert values['techniview_submissions{status="running",practice_run="false"}'] == 6
    assert values['techniview_submissions{status="passed",practice_run="false"}'] == 1
    assert values["techniview_submission_queue_depth"] == 1
    assert 120 <= values["techniview_submission_queue_oldest_seconds"] < 150
    assert values["techniview_runner_dispatch_retries"] == 2
    assert values["techniview_runner_poll_failures"] == 2
    assert values["techniview_runner_busy_submissions"] == 1
    assert values["techniview_runner_unknown_outcomes"] == 1
    for private_value in (
        "private-",
        student.email,
        student.name,
        "callback_token",
        "source_code",
        "stdout",
        "stderr",
    ):
        assert private_value not in payload


def test_empty_execution_queue_exports_numeric_zeroes(metrics_database):
    values = samples(metrics.metrics().body.decode())
    execution_values = [
        value
        for key, value in values.items()
        if key.startswith("techniview_execution_cases{")
    ]
    assert len(execution_values) == 6
    assert execution_values == [0] * 6
    assert values["techniview_submission_queue_depth"] == 0
    assert values["techniview_submission_queue_oldest_seconds"] == 0


def test_http_metrics_aggregate_across_processes(tmp_path):
    path = str(tmp_path / "http-metrics.sqlite3")
    HttpMetrics(path)
    context = get_context("spawn")
    workers = [
        context.Process(target=_observe_http_requests, args=(path, 25))
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    payload = HttpMetrics(path).render()
    values = samples(payload)
    assert (
        values[
            'techniview_http_requests_total{method="GET",route="/api/health/ready",status="200"}'
        ]
        == 50
    )
    assert (
        values[
            'techniview_http_request_duration_seconds_count{method="GET",route="/api/health/ready",status="200"}'
        ]
        == 50
    )


def test_http_metrics_initialize_concurrently(tmp_path):
    path = str(tmp_path / "http-metrics.sqlite3")
    context = get_context("spawn")
    worker_count = 16
    start_gate = context.Barrier(worker_count)
    workers = [
        context.Process(target=_initialize_http_metrics, args=(path, start_gate))
        for _ in range(worker_count)
    ]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 15
    for worker in workers:
        worker.join(timeout=max(0, deadline - time.monotonic()))
    for worker in workers:
        if worker.is_alive():
            worker.terminate()
            worker.join()
        assert worker.exitcode == 0
    assert "techniview_http_requests_total" in HttpMetrics(path).render()


@pytest.mark.anyio
async def test_http_metric_writer_lock_does_not_block_event_loop(tmp_path, monkeypatch):
    path = str(tmp_path / "http-metrics.sqlite3")
    shared_metrics = HttpMetrics(path)
    writer_lock = sqlite3.connect(path, timeout=5, check_same_thread=False)
    writer_lock.execute("BEGIN IMMEDIATE")
    writer_attempted = threading.Event()
    persist = shared_metrics._write_observation

    def mark_writer_attempt(*observation):
        writer_attempted.set()
        persist(*observation)

    monkeypatch.setattr(shared_metrics, "_write_observation", mark_writer_attempt)
    monkeypatch.setattr(observability, "http_metrics", shared_metrics)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def send(_message):
        return None

    middleware = RequestObservabilityMiddleware(app)
    scope = {
        "type": "http",
        "method": "GET",
        "route": type("Route", (), {"path": "/contention"})(),
    }
    timer = threading.Timer(0.6, writer_lock.commit)
    started = time.perf_counter()
    timer.start()
    try:
        request = asyncio.create_task(middleware(scope, None, send))
        await asyncio.sleep(0.05)
        assert writer_attempted.is_set()
        event_loop_delay = time.perf_counter() - started
        scrape_started = time.perf_counter()
        scrape_payload = shared_metrics.render()
        scrape_duration = time.perf_counter() - scrape_started
        await request
        assert event_loop_delay < 0.3
        assert scrape_duration < 0.3
        assert samples(scrape_payload)["techniview_http_metrics_dropped_total"] == 0
    finally:
        timer.cancel()
        writer_lock.close()
        shared_metrics._write_queue.join()
    values = samples(shared_metrics.render())
    assert values["techniview_http_metrics_dropped_total"] == 0
    assert (
        values[
            'techniview_http_requests_total{method="GET",route="/contention",status="200"}'
        ]
        == 1
    )


def test_dropped_http_metrics_aggregate_across_processes(tmp_path):
    path = str(tmp_path / "http-metrics.sqlite3")
    HttpMetrics(path)
    context = get_context("spawn")
    workers = [
        context.Process(target=_saturate_http_metrics, args=(path,)) for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0

    values = samples(HttpMetrics(path).render())
    assert values["techniview_http_metrics_dropped_total"] == 2
    assert (
        values[
            'techniview_http_requests_total{method="GET",route="/api/health/ready",status="200"}'
        ]
        == 4
    )


def test_submission_view_reports_wait_and_execution_durations(metrics_database):
    db = metrics_database
    student = db.scalar(select(User).where(User.email == "student@techniview.local"))
    case = db.scalar(select(ProblemTestCase).order_by(ProblemTestCase.id))
    submitted_at = datetime(2026, 10, 30, 12, 0, 0)
    started_at = submitted_at + timedelta(seconds=7)
    completed_at = started_at + timedelta(seconds=25)
    submission = Submission(
        student_id=student.id,
        problem_id=case.problem_id,
        source_code="pass",
        status=SubmissionStatus.PASSED,
        submitted_at=submitted_at,
        started_at=started_at,
        completed_at=completed_at,
    )
    db.add(submission)
    db.flush()

    response = _submission_response(submission)

    assert response["submitted_at"] == submitted_at
    assert response["started_at"] == started_at
    assert response["completed_at"] == completed_at
    assert response["wait_seconds"] == 7
    assert response["execution_seconds"] == 25


def test_completed_legacy_submission_without_start_time_has_unknown_wait(
    metrics_database,
):
    db = metrics_database
    student = db.scalar(select(User).where(User.email == "student@techniview.local"))
    case = db.scalar(select(ProblemTestCase).order_by(ProblemTestCase.id))
    submitted_at = datetime(2026, 10, 29, 12, 0, 0)
    completed_at = submitted_at + timedelta(seconds=45)
    submission = Submission(
        student_id=student.id,
        problem_id=case.problem_id,
        source_code="pass",
        status=SubmissionStatus.PASSED,
        submitted_at=submitted_at,
        completed_at=completed_at,
    )
    db.add(submission)
    db.flush()

    response = _submission_response(submission)

    assert response["started_at"] is None
    assert response["wait_seconds"] is None
    assert response["execution_seconds"] is None
