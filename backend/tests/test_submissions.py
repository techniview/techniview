from contextlib import nullcontext
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.core.observability import HttpMetrics
from app.models import (
    AssignmentItem,
    StudentPracticeProgress,
    Submission,
    SubmissionCaseResult,
)
from app.routers import metrics
from app.routers.submissions import get_status_message
from app.services.progress import utc_now
from app.worker.submissions import process_next_submission
from sqlalchemy import select

pytestmark = pytest.mark.anyio


def _run(db, reports):
    with patch("app.core.go_judge.execute", side_effect=reports) as execute:
        assert process_next_submission(db, "test-worker") is True
    return execute


async def _problem_id(client, title):
    problems = (await client.get("/api/problems")).json()["items"]
    return next(item["id"] for item in problems if item["title"] == title)


async def test_status_messages_cover_all_known_ids():
    for status_id in range(1, 15):
        msg = get_status_message(status_id)
        assert isinstance(msg, str) and "Unknown" not in msg
    assert "Unknown" in get_status_message(999)


@pytest.mark.parametrize(
    "extra",
    [
        {"source_code": ""},
        {"language_id": 54},
        {"stdin": "x", "expected_output": "x", "cpu_time_limit": 1000},
    ],
)
async def test_submission_rejects_client_owned_fields(student_client, extra):
    problem_id = await _problem_id(student_client, "Sum a List")
    payload = {"problem_id": problem_id, "source_code": "print(1)", **extra}
    assert (
        await student_client.post(
            "/api/submissions",
            json=payload,
            headers={"Idempotency-Key": uuid4().hex},
        )
    ).status_code == 422


async def test_get_rejects_bad_id(student_client):
    assert (await student_client.get("/api/submissions/not-an-id")).status_code == 422


async def test_worker_runs_server_cases_and_redacts_hidden_case(
    student_client, db_session
):
    problem_id = await _problem_id(student_client, "Sum a List")
    created = await student_client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "problem_id": problem_id,
            "source_code": "def sum_list(values): return sum(values)",
        },
    )
    assert created.status_code == 202
    reports = [
        {
            "token": "public-token",
            "status": {"id": 3},
            "stdout": "6\n",
            "time": "0.125",
            "memory": 42.2,
        },
        {"token": "hidden-token", "status": {"id": 4}, "stdout": "wrong\n"},
    ]
    execute = _run(db_session, reports)
    body = (await student_client.get(f"/api/submissions/{created.json()['id']}")).json()
    assert body["status"] == "failed"
    assert body["score"] == 0.5
    assert body["passed_count"] == 1 and body["test_count"] == 2
    assert len(body["public_results"]) == 1
    assert body["public_results"][0]["stdout"] == "6\n"
    assert body["public_results"][0]["execution_time_ms"] == 125
    assert "wrong\n" not in str(body)
    assert "[[-2, 2]]" not in str(body)
    assert execute.call_count == 2
    assert [call.args[0].expected for call in execute.call_args_list] == ["6", "0"]


async def test_running_worker_is_not_counted_in_submission_queue(
    student_client, db_session, monkeypatch
):
    problem_id = await _problem_id(student_client, "Count Evens")
    created = await student_client.post(
        "/api/submissions",
        json={"problem_id": problem_id, "source_code": "print(42)"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 202
    monkeypatch.setattr(metrics, "SessionLocal", lambda: nullcontext(db_session))
    monkeypatch.setattr(metrics, "http_metrics", HttpMetrics())
    observed = set()

    def inspect_metrics(_execution):
        payload = metrics.metrics().body.decode()
        observed.update(
            line
            for line in payload.splitlines()
            if line.startswith("techniview_submission_queue_depth ")
            or line.startswith("techniview_submission_queue_oldest_seconds ")
            or line.startswith(
                'techniview_execution_cases{phase="running_on_go_judge"}'
            )
        )
        return {"status": {"id": 3}, "stdout": "2\n", "time": 0.01}

    with patch("app.core.go_judge.execute", side_effect=inspect_metrics):
        assert process_next_submission(db_session, "test-worker") is True

    assert "techniview_submission_queue_depth 0" in observed
    assert "techniview_submission_queue_oldest_seconds 0.000" in observed
    assert 'techniview_execution_cases{phase="running_on_go_judge"} 1' in observed


async def test_direct_execution_updates_progress_once(student_client, db_session):
    problem_id = await _problem_id(student_client, "Count Evens")
    created = await student_client.post(
        "/api/submissions",
        json={"problem_id": problem_id, "source_code": "print(42)"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 202
    _run(db_session, [{"status": {"id": 3}, "stdout": "2\n", "time": 0.01}])
    row = db_session.get(Submission, created.json()["id"])
    assert (await student_client.get(f"/api/submissions/{row.id}")).json()["done"]
    retry = await student_client.post(
        "/api/submissions",
        json={"problem_id": problem_id, "source_code": "print(0)"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    _run(db_session, [{"status": {"id": 4}, "stdout": "0\n", "time": 0.01}])
    assert retry.status_code == 202
    student_id = (await student_client.get("/api/auth/me")).json()["id"]
    db_session.expire_all()
    progress = db_session.get(StudentPracticeProgress, (student_id, problem_id))
    assert progress.valid_attempt_count == 2
    assert progress.retry_count == 1
    assert progress.wrong_answer_count == 1


async def test_public_run_idempotency_reuses_only_the_same_action(
    student_client, db_session
):
    problem_id = await _problem_id(student_client, "Sum a List")
    payload = {"source_code": "def sum_list(values): return sum(values)"}
    key = uuid4().hex
    first = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    retry = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == retry.status_code == 202
    assert first.json()["id"] == retry.json()["id"]
    assert db_session.query(Submission).filter_by(is_practice_run=True).count() == 1

    changed = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json={"source_code": "def sum_list(values): return 0"},
        headers={"Idempotency-Key": key},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_key_reused"

    intentional_repeat = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json=payload,
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert intentional_repeat.status_code == 202
    assert intentional_repeat.json()["id"] != first.json()["id"]


async def test_expired_idempotency_key_creates_a_new_run(student_client, db_session):
    from app.models import SubmissionIdempotencyKey

    problem_id = await _problem_id(student_client, "Sum a List")
    key = uuid4().hex
    payload = {"source_code": "def sum_list(values): return sum(values)"}
    first = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    record = db_session.query(SubmissionIdempotencyKey).one()
    record.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    retry_after_expiry = await student_client.post(
        f"/api/problems/{problem_id}/run",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert retry_after_expiry.status_code == 202
    assert retry_after_expiry.json()["id"] != first.json()["id"]


async def test_attempt_limit_counts_queued_reservation(student_client, db_session):
    course_id = (await student_client.get("/api/courses")).json()["items"][0]["id"]
    assignment = (
        await student_client.get(f"/api/courses/{course_id}/assignments")
    ).json()["items"][0]
    item_data = assignment["items"][1]
    item = db_session.get(AssignmentItem, item_data["id"])
    item.submission_limit = 1
    db_session.commit()
    payload = {
        "problem_id": item.problem_id,
        "assignment_item_id": item.id,
        "source_code": "def count_evens(values): return 0",
    }
    first = await student_client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json=payload,
    )
    second = await student_client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json=payload,
    )
    assert first.status_code == 202 and second.status_code == 409
    assert second.json()["error"]["code"] == "active_submission"
    assert (
        db_session.scalar(
            select(SubmissionCaseResult).where(
                SubmissionCaseResult.submission_id == first.json()["id"]
            )
        )
        is not None
    )


async def test_graded_submission_idempotency_precedes_active_attempt_conflict(
    student_client, db_session
):
    problem_id = await _problem_id(student_client, "Sum a List")
    payload = {
        "problem_id": problem_id,
        "source_code": "def sum_list(values): return sum(values)",
    }
    key = uuid4().hex
    first = await student_client.post(
        "/api/submissions", json=payload, headers={"Idempotency-Key": key}
    )
    retry = await student_client.post(
        "/api/submissions", json=payload, headers={"Idempotency-Key": key}
    )
    assert first.status_code == retry.status_code == 202
    assert first.json()["id"] == retry.json()["id"]
    assert db_session.query(Submission).filter_by(is_practice_run=False).count() == 1

    changed = await student_client.post(
        "/api/submissions",
        json={**payload, "source_code": "def sum_list(values): return 0"},
        headers={"Idempotency-Key": key},
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_key_reused"


async def test_runner_reported_unknown_outcome_is_retryable(student_client, db_session):
    from app.core import go_judge

    problem_id = await _problem_id(student_client, "Sum a List")
    response = await student_client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={"problem_id": problem_id, "source_code": "def solve(values): return 0"},
    )
    assert response.status_code == 202
    submission_id = response.json()["id"]
    with patch("app.core.go_judge.execute", side_effect=go_judge.OutcomeUnknown):
        assert process_next_submission(db_session, "unknown-worker")
    result = (await student_client.get(f"/api/submissions/{submission_id}")).json()
    assert result["failure_code"] == "runner_outcome_unknown"
    assert result["retryable"] is True
    assert result["score"] is None
