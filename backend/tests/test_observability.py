from datetime import UTC, datetime, timedelta

import pytest
from app.core.observability import HttpMetrics
from app.models import (
    ProblemTestCase,
    Submission,
    SubmissionStatus,
    User,
)
from app.routers import metrics
from app.services.execution import snapshot_case_result
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


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
        db.add(
            snapshot_case_result(
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
        )
    completed = Submission(
        student_id=student.id,
        problem_id=case.problem_id,
        source_code="private-completed-source",
        status=SubmissionStatus.PASSED,
    )
    db.add(completed)
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
        "sending_to_judge0": 1,
        "waiting_on_judge0": 2,
        "running_on_judge0": 2,
        "infrastructure_errors": 1,
    }.items():
        assert values[f'techniview_execution_cases{{phase="{phase}"}}'] == count
    assert values['techniview_submissions{status="queued",practice_run="true"}'] == 1
    assert values['techniview_submissions{status="running",practice_run="false"}'] == 6
    assert values['techniview_submissions{status="passed",practice_run="false"}'] == 1
    assert values["techniview_submission_queue_depth"] == 1
    assert 120 <= values["techniview_submission_queue_oldest_seconds"] < 150
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


def test_http_histogram_is_cumulative_includes_overflow_and_escapes_labels():
    registry = HttpMetrics()
    route = '/api/"quoted"/\\path\nnext'
    for duration in (0.005, 0.02, 7):
        registry.observe("GET", route, 200, duration)
    registry.observe("GET", route, 500, 0.1)
    payload = registry.render()
    values = samples(payload)
    labels = 'method="GET",route="/api/\\"quoted\\"/\\\\path\\nnext",status="200"'
    prefix = "techniview_http_request_duration_seconds"
    assert values[f"techniview_http_requests_total{{{labels}}}"] == 3
    for bound, count in (
        ("0.005", 1),
        ("0.01", 1),
        ("0.025", 2),
        ("5", 2),
        ("+Inf", 3),
    ):
        assert values[f'{prefix}_bucket{{{labels},le="{bound}"}}'] == count
    assert values[f"{prefix}_count{{{labels}}}"] == 3
    assert values[f"{prefix}_sum{{{labels}}}"] == pytest.approx(7.025)
    error_labels = labels.replace('status="200"', 'status="500"')
    assert values[f"techniview_http_requests_total{{{error_labels}}}"] == 1
    assert "\nnext" not in payload
