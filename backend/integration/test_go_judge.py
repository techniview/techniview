"""Real sandbox probes in the disposable integration stack."""

import os
import time
from uuid import uuid4

import pytest
from app.core import go_judge
from app.models import Problem, Submission
from integration import test_submission_mysql as fixtures
from sqlalchemy import select

client = fixtures.client
database = fixtures.database

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1",
    reason="requires direct integration stack",
)


@pytest.mark.parametrize(
    "source,expected,code,cpu,memory",
    [
        ("print(42)", "42", 3, 2, 128000),
        ("print(41)", "42", 4, 2, 128000),
        ('raise ValueError("probe")', "", 11, 2, 128000),
        ("import os; os._exit(7)", "", 11, 2, 128000),
        ("while True: pass", "", 5, 0.1, 128000),
        ('x = bytearray(256*1024*1024); print("bad")', "", 12, 2, 32768),
        ('print("x" * (2*1024*1024))', "", 8, 2, 128000),
        ('import os; print(os.path.exists("/api"))', "False", 3, 2, 128000),
    ],
)
def test_direct_sandbox_limits(source, expected, code, cpu, memory):
    report = go_judge.execute(go_judge.Execution(source, "", expected, cpu, memory))
    if memory == 32768:
        # Strict allocation denial can surface as Python MemoryError or OOM kill.
        assert report["status"]["id"] in (11, 12), report
    elif code == 8:
        # RLIMIT_FSIZE may surface as Python OSError before collector termination.
        assert report["status"]["id"] in (8, 11), report
        assert len(report["stdout"].encode()) <= 1024 * 1024
    else:
        assert report["status"]["id"] == code, report
    assert report["stdout"] != "bad\n"


def test_direct_cases_are_fresh():
    first = (
        "import collections; collections.marker=True; "
        'open("/tmp/marker", "w").write("x")'
    )
    second = (
        'import collections, os; print(hasattr(collections,"marker"), '
        'os.path.exists("/tmp/marker"))'
    )
    assert (
        go_judge.execute(go_judge.Execution(first, "", "", 2, 128000))["status"]["id"]
        == 3
    )
    assert (
        go_judge.execute(go_judge.Execution(second, "", "False False", 2, 128000))[
            "status"
        ]["id"]
        == 3
    )


@pytest.mark.skipif(
    os.getenv("DIRECT_RESTART_TEST") != "1", reason="requires host restart control"
)
def test_direct_worker_restart(database, client):
    problem = database.scalar(select(Problem).where(Problem.title == "Sum a List"))
    response = client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "problem_id": problem.id,
            "source_code": (
                "import time\ndef sum_list(v):\n    time.sleep(3)\n    return sum(v)"
            ),
        },
    )
    response.raise_for_status()
    sid = response.json()["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        database.rollback()
        database.expire_all()
        row = database.get(Submission, sid)
        if any(c.dispatch_started_at for c in row.case_results):
            print("DIRECT_RESTART_READY", flush=True)
            break
        time.sleep(0.05)
    else:
        pytest.fail("case was never dispatched")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        database.rollback()
        database.expire_all()
        row = database.get(Submission, sid)
        if row.completed_at:
            break
        time.sleep(0.2)
    else:
        pytest.fail("submission never recovered")
    assert row.failure_code == "runner_outcome_unknown"
    assert all(c.dispatch_attempt_count == 1 for c in row.case_results)
    assert any(c.judge0_status_id == 13 for c in row.case_results)
    assert any(c.judge0_status_id == 3 for c in row.case_results)
