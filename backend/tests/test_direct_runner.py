from datetime import timedelta
from uuid import uuid4

import pytest
from app.core import go_judge
from app.core.config import settings
from app.models import Submission
from app.services.progress import utc_now
from app.worker.submissions import process_next_submission

pytestmark = pytest.mark.anyio


async def queue(client):
    problems = (await client.get("/api/problems")).json()["items"]
    problem = next(p for p in problems if p["title"] == "Sum a List")
    response = await client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "problem_id": problem["id"],
            "source_code": "def sum_list(v): return sum(v)",
        },
    )
    assert response.status_code == 202
    return response.json()["id"]


def passed(execution):
    return {
        "status": {"id": 3},
        "stdout": execution.expected,
        "time": 0.01,
        "memory": 128,
    }


async def test_direct_persists_results_without_callbacks(
    student_client, db_session, monkeypatch
):
    monkeypatch.setattr(go_judge, "execute", passed)
    sid = await queue(student_client)
    assert process_next_submission(db_session, "first")
    row = db_session.get(Submission, sid)
    assert row.status == "passed"
    assert all(c.dispatch_attempt_count == 1 for c in row.case_results)
    assert not process_next_submission(db_session, "second")


async def test_direct_crash_never_reexecutes_started_case(
    student_client, db_session, monkeypatch
):
    sid = await queue(student_client)
    calls = []

    def crash(execution):
        calls.append(execution)
        raise SystemExit("simulated process death after dispatch")

    monkeypatch.setattr(go_judge, "execute", crash)
    with pytest.raises(SystemExit):
        process_next_submission(db_session, "first")
    row = db_session.get(Submission, sid)
    row.claimed_at = utc_now() - timedelta(seconds=settings.WORKER_LEASE_SECONDS + 1)
    db_session.commit()

    def complete(execution):
        calls.append(execution)
        return passed(execution)

    monkeypatch.setattr(go_judge, "execute", complete)
    assert process_next_submission(db_session, "replacement")
    row = db_session.get(Submission, sid)
    assert row.failure_code == "runner_outcome_unknown"
    assert len(calls) == len(row.case_results)
    assert sum(c.judge0_status_id == 13 for c in row.case_results) == 1


@pytest.mark.parametrize("report", [None, {}, {"time": -1}, {"files": None}])
def test_malformed_result_is_not_a_verdict(report):
    case = go_judge.Execution("pass", "", "", 2, 128000)
    with pytest.raises((ValueError, KeyError, TypeError)):
        go_judge.grade(case, report, 1024)
