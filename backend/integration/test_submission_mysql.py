"""Run only in the disposable compose.integration.yml stack."""

import os
import time
from concurrent.futures import ThreadPoolExecutor
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


@pytest.fixture(scope="module")
def client():
    deadline = time.monotonic() + 90
    with httpx.Client(timeout=5) as runner:
        while True:
            try:
                runner.get("http://go-judge:5050/version").raise_for_status()
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
def test_go_judge_finishes_without_api_polling(database, client, source, expected):
    from app.models import Problem, Submission

    problem = database.scalar(select(Problem).where(Problem.title == "Sum a List"))
    response = client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
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
            "go-judge execution did not finalize the submission"
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


@pytest.mark.parametrize(
    "source", ["a" * 65536, "é" * 32768], ids=["ascii-overflow", "utf8-overflow"]
)
def test_source_byte_overflow_is_http_422(client, source):
    response = client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
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
    from app.models import Problem, Submission, User, UserRole

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
                headers={"Idempotency-Key": uuid4().hex},
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


def test_competing_workers_claim_a_submission_once(database, client):
    from datetime import UTC, datetime

    from app.core.db import SessionLocal
    from app.models import Problem, Submission, SubmissionStatus
    from app.worker.submissions import claim_submission

    problem = database.scalar(select(Problem).where(Problem.title == "Count Evens"))
    created = client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={"problem_id": problem.id, "source_code": "print(1)"},
    )
    created.raise_for_status()
    submission_id = created.json()["id"]

    def claim(owner):
        with SessionLocal() as db:
            return claim_submission(db, owner, submission_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, ("worker-a", "worker-b")))
    assert claimed.count(submission_id) == 1
    assert claimed.count(None) == 1

    database.rollback()
    submission = database.get(Submission, submission_id)
    submission.status = SubmissionStatus.INFRASTRUCTURE_ERROR
    submission.completed_at = datetime.now(UTC).replace(tzinfo=None)
    submission.claim_owner = None
    submission.claimed_at = None
    database.commit()


def test_concurrent_retries_with_one_idempotency_key_create_one_run(database, client):
    from app.core.config import settings
    from app.models import Problem

    key = uuid4().hex
    cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
    problem = database.scalar(select(Problem).where(Problem.title == "Count Evens"))
    problem_id = problem.id

    def submit(_):
        with httpx.Client(
            base_url="http://backend:8000",
            timeout=30,
            cookies={settings.SESSION_COOKIE_NAME: cookie},
        ) as api:
            return api.post(
                "/api/submissions",
                headers={"Idempotency-Key": key},
                json={"problem_id": problem_id, "source_code": "print(1)"},
            )

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(submit, range(8)))
    assert all(response.status_code == 202 for response in responses), [
        (response.status_code, response.text) for response in responses
    ]
    assert len({response.json()["id"] for response in responses}) == 1
