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
