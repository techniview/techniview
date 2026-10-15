"""Run only in the disposable compose.integration.yml stack."""

import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    os.getenv("INTEGRATION_TESTS") != "1", reason="requires isolated integration stack"
)


@pytest.fixture
def database():
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        assert db.scalar(text("SELECT DATABASE()")) == "integration"
        assert db.scalar(text("SELECT @@transaction_isolation")) == "REPEATABLE-READ"
        yield db


def test_overlapping_callbacks_use_current_mysql_rows(database, monkeypatch):
    from app.core.db import SessionLocal
    from app.core.security import hash_token
    from app.models import Problem, StudentPracticeProgress, SubmissionCaseResult, User
    from app.routers import submissions

    user = database.scalar(select(User).where(User.email == "student@techniview.local"))
    problem = database.scalar(select(Problem).where(Problem.title == "Sum a List"))
    submission = submissions._reserve_submission(
        database,
        submissions.SubmissionCreate(source_code="pass", problem_id=problem.id),
        user.id,
    )
    credentials = [
        (secrets.token_urlsafe(32), str(uuid4())) for _ in problem.test_cases
    ]
    for case, (secret, token) in zip(problem.test_cases, credentials, strict=True):
        database.add(
            SubmissionCaseResult(
                submission_id=submission.id,
                test_case_id=case.id,
                callback_token_hash=hash_token(secret),
                judge0_token=token,
                judge0_status_id=1,
            )
        )
    database.commit()
    progress_key = (user.id, problem.id)
    attempts = database.get(StudentPracticeProgress, progress_key).valid_attempt_count
    database.rollback()

    # Both callbacks perform their initial snapshot read before either locks the parent.
    rendezvous = Barrier(2, timeout=15)
    original_load = submissions._load_submission

    def synchronized_load(db, submission_id):
        rendezvous.wait()
        return original_load(db, submission_id)

    monkeypatch.setattr(submissions, "_load_submission", synchronized_load)

    def deliver(credential):
        secret, token = credential
        with SessionLocal() as db:
            return submissions.receive_judge0_callback(
                secret,
                {
                    "token": token,
                    "status": {"id": 3},
                    "stdout": "Mgo=",
                    "time": "0.001",
                    "memory": 1024,
                },
                db,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(deliver, credentials)) == [{"ok": True}] * 2
    monkeypatch.setattr(submissions, "_load_submission", original_load)
    database.expire_all()
    assert submission.status == "passed"
    assert submission.score == Decimal("1")
    assert all(result.stdout == "2\n" for result in submission.case_results)
    assert (
        database.get(StudentPracticeProgress, progress_key).valid_attempt_count
        == attempts + 1
    )
    for credential in credentials:
        deliver(credential)
    database.rollback()
    database.expire_all()
    assert (
        database.get(StudentPracticeProgress, progress_key).valid_attempt_count
        == attempts + 1
    )


@pytest.fixture(scope="module")
def client():
    deadline = time.monotonic() + 90
    with httpx.Client(timeout=5) as runner:
        while True:
            try:
                runner.get("http://judge:2358/about").raise_for_status()
                break
            except httpx.HTTPError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
    with httpx.Client(base_url="http://backend:8000", timeout=30) as api:
        response = api.post(
            "/api/auth/login",
            json={
                "email": "student@techniview.local",
                "password": "student-demo",
            },
        )
        response.raise_for_status()
        yield api


@pytest.mark.parametrize(
    "source,expected",
    [
        ("def sum_list(values):\n    return sum(values)", "passed"),
        ("def sum_list(values):\n    return 999", "failed"),
        ("def sum_list(values):\n    raise ValueError('integration')", "runtime_error"),
    ],
)
def test_real_judge0_callback_finishes_without_api_polling(
    database, client, source, expected
):
    from app.models import Problem, Submission

    problem = database.scalar(select(Problem).where(Problem.title == "Sum a List"))
    response = client.post(
        "/api/submissions",
        json={
            "problem_id": problem.id,
            "source_code": source,
        },
    )
    response.raise_for_status()
    submission_id = response.json()["id"]
    deadline = time.monotonic() + 60
    while True:
        # End each read transaction so the test itself does not retain a snapshot.
        database.rollback()
        submission = database.get(Submission, submission_id)
        if submission.completed_at is not None:
            break
        assert time.monotonic() < deadline, (
            "Judge0 callback did not finalize the submission"
        )
        time.sleep(0.2)
    assert submission.status == expected
    assert len(submission.case_results) == 2
    for result in submission.case_results:
        assert result.execution_time_ms is not None
        assert result.memory_kb is not None
        if expected == "runtime_error":
            assert "ValueError: integration" in result.stderr
        else:
            assert result.stdout.endswith("\n")
            if expected == "failed":
                assert result.stdout == "999\n"
    if expected == "passed":
        assert {result.stdout for result in submission.case_results} == {"6\n", "0\n"}


def test_polling_recovers_execution_without_callback(database, client):
    from app.core.judge0 import judge0_get, judge0_submit
    from app.models import Problem, SubmissionCaseResult, User
    from app.routers.submissions import SubmissionCreate, _reserve_submission
    from app.services.execution import build_case_execution
    from app.services.progress import utc_now

    user = database.scalar(select(User).where(User.email == "student@techniview.local"))
    problem = database.scalar(select(Problem).where(Problem.title == "Count Evens"))
    source = "def count_evens(values):\n    return sum(x % 2 == 0 for x in values)"
    submission = _reserve_submission(
        database,
        SubmissionCreate(
            source_code=source,
            problem_id=problem.id,
        ),
        user.id,
    )
    case = problem.test_cases[0]
    execution = build_case_execution(problem, case, source)
    result = judge0_submit(
        execution.source_code,
        stdin=execution.stdin,
        expected_output=execution.expected_output,
        wait=False,
    )
    token = result["token"]
    database.add(
        SubmissionCaseResult(
            submission_id=submission.id,
            test_case_id=case.id,
            judge0_token=token,
            judge0_status_id=1,
            dispatch_started_at=utc_now(),
        )
    )
    database.commit()
    deadline = time.monotonic() + 60
    while judge0_get(token)["status"]["id"] < 3:
        assert time.monotonic() < deadline, "Judge0 execution never completed"
        time.sleep(0.2)
    # Student GET is read-only; the application worker completes missed callbacks.
    while True:
        database.rollback()
        database.expire_all()
        if submission.status == "passed":
            break
        assert time.monotonic() < deadline, "Worker did not recover missing callback"
        time.sleep(0.2)
    response = client.get(f"/api/submissions/{submission.id}")
    response.raise_for_status()
    assert response.json()["status"] == "passed"
    assert submission.case_results[0].stdout == "2\n"


@pytest.mark.parametrize(
    "source", ["a" * 65536, "é" * 32768], ids=["ascii-overflow", "utf8-overflow"]
)
def test_source_byte_overflow_is_http_422(client, source):
    response = client.post(
        "/api/submissions",
        json={
            "problem_id": 1,
            "source_code": source,
        },
    )
    assert response.status_code == 422


def test_fifty_near_simultaneous_requests_finish_once(database):
    """One class-sized burst keeps each logical attempt and result durable."""
    from datetime import UTC, datetime

    from app.core.config import settings
    from app.core.security import create_session, hash_password
    from app.models import Problem, Submission, SubmissionCaseResult, User, UserRole

    problem = database.scalar(select(Problem).where(Problem.title == "Count Evens"))
    batch = uuid4().hex
    users = [
        User(
            name=f"Burst student {index}",
            email=f"burst-{batch}-{index}@example.test",
            password_hash=hash_password("burst-test-password"),
            role=UserRole.STUDENT,
            email_verified_at=datetime.now(UTC).replace(tzinfo=None),
        )
        for index in range(50)
    ]
    database.add_all(users)
    database.commit()
    credentials = [create_session(database, user)[0] for user in users]
    source = "def count_evens(values):\n    return sum(x % 2 == 0 for x in values)"

    def submit(token):
        with httpx.Client(
            base_url="http://backend:8000",
            timeout=30,
            cookies={settings.SESSION_COOKIE_NAME: token},
        ) as api:
            response = api.post(
                "/api/submissions",
                json={"problem_id": problem.id, "source_code": source},
            )
            return response

    with ThreadPoolExecutor(max_workers=50) as executor:
        results = list(executor.map(submit, credentials))
    assert all(response.status_code == 202 for response in results), [
        (response.status_code, response.text) for response in results
    ]
    ids = {response.json()["id"] for response in results}
    assert len(ids) == 50
    deadline = time.monotonic() + 120
    while True:
        database.rollback()
        submissions = database.scalars(
            select(Submission).where(Submission.id.in_(ids))
        ).all()
        if len(submissions) == 50 and all(row.completed_at for row in submissions):
            break
        assert time.monotonic() < deadline, "Fifty submissions did not finish"
        time.sleep(0.25)
    assert all(row.status == "passed" for row in submissions)
    cases = database.scalars(
        select(SubmissionCaseResult).where(SubmissionCaseResult.submission_id.in_(ids))
    ).all()
    assert len(cases) == 50
    assert len({case.judge0_token for case in cases}) == 50
