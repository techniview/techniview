import json
from datetime import timedelta

import httpx
import pytest
from app.core.config import settings
from app.core.security import hash_token
from app.models import AccountToken, CourseEnrollment, CourseMembership, EmailJob, User
from app.services.account_recovery import account_token_value, now_utc
from app.services.email_delivery import enrollment_token_value, process_email_jobs
from sqlalchemy import select

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def capture_email(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "EMAIL_DELIVERY_MODE", "capture")
    monkeypatch.setattr(
        settings, "EMAIL_SIGNING_KEY", "test-signing-key-with-at-least-32-characters"
    )
    monkeypatch.setattr(settings, "EMAIL_CAPTURE_DIR", str(tmp_path))


async def test_course_creation_rotation_and_archive(teacher_client, student_client):
    created = await teacher_client.post("/api/courses", json={"name": "New course"})
    assert created.status_code == 201
    data = created.json()
    course_id = data["course"]["id"]
    token = data["join_token"]
    assert (
        await student_client.post("/api/courses", json={"name": "No"})
    ).status_code == 403
    assert (await student_client.get(f"/api/join/{token}")).status_code == 200
    rotated = await teacher_client.post(f"/api/courses/{course_id}/join-link")
    assert rotated.status_code == 200
    assert (await student_client.get(f"/api/join/{token}")).status_code == 404
    assert (
        await teacher_client.post(f"/api/courses/{course_id}/archive")
    ).status_code == 200
    assert (
        await teacher_client.put(f"/api/courses/{course_id}", json={"name": "No"})
    ).status_code == 409
    assert (
        await teacher_client.post(f"/api/courses/{course_id}/join-link")
    ).status_code == 409
    assert (await teacher_client.get(f"/api/courses/{course_id}")).status_code == 200


async def test_csv_duplicates_atomic_and_pending_signup(
    teacher_client, client, db_session
):
    endpoint = "/api/courses/1/enrollments/import"
    duplicate = await teacher_client.post(
        endpoint, json={"csv": "name,email\nOne,new@example.com\nTwo,NEW@example.com\n"}
    )
    assert duplicate.status_code == 422
    assert db_session.scalar(select(CourseEnrollment)) is None
    response = await teacher_client.post(
        endpoint,
        json={
            "csv": (
                "name,email\nExisting,student@techniview.local\nNew,new@example.com\n"
            )
        },
    )
    assert response.status_code == 200
    assert response.json() == {"enrolled": 1, "pending_signup": 1}
    pending = db_session.scalar(select(CourseEnrollment))
    token = enrollment_token_value(pending)
    assert pending.token_hash == hash_token(token)
    wrong_email = await client.post(
        f"/api/join/{token}/signup",
        json={
            "name": "Wrong",
            "email": "wrong@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert wrong_email.status_code == 404
    signup = await client.post(
        f"/api/join/{token}/signup",
        json={
            "name": "New",
            "email": "new@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert signup.status_code == 202
    user = db_session.scalar(select(User).where(User.email == "new@example.com"))
    assert user.email_verified_at is None
    assert (
        db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == user.id)
        )
        is None
    )
    verification = db_session.scalar(
        select(AccountToken).where(AccountToken.user_id == user.id)
    )
    verify = await client.post(
        "/api/auth/verify-email", json={"token": account_token_value(verification)}
    )
    assert verify.status_code == 200
    assert (
        db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == user.id)
        )
        is not None
    )
    replay = await client.post(
        "/api/auth/verify-email", json={"token": account_token_value(verification)}
    )
    assert replay.status_code == 400


async def test_password_reset_revokes_sessions_and_tokens(
    client, student_client, db_session, tmp_path
):
    unknown = await client.post(
        "/api/auth/password-recovery", json={"email": "unknown@example.com"}
    )
    known = await client.post(
        "/api/auth/password-recovery", json={"email": "student@techniview.local"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    record = db_session.scalar(
        select(AccountToken).where(AccountToken.purpose == "reset")
    )
    token = account_token_value(record)
    assert record.token_hash == hash_token(token)
    assert process_email_jobs(db_session) == 1
    captures = list(tmp_path.glob("*.json"))
    assert len(captures) == 1
    assert token in json.loads(captures[0].read_text())["text"]
    reset = await client.post(
        "/api/auth/password-reset",
        json={
            "token": token,
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )
    assert reset.status_code == 204
    assert (await student_client.get("/api/auth/me")).status_code == 401
    assert (
        await client.post(
            "/api/auth/password-reset",
            json={
                "token": token,
                "password": "newpassword123",
                "password_confirm": "newpassword123",
            },
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/auth/login",
            json={"email": "student@techniview.local", "password": "newpassword123"},
        )
    ).status_code == 200


async def test_email_failures_retry_then_stop(client, db_session, monkeypatch):
    from app.services import email_delivery

    await client.post(
        "/api/auth/password-recovery", json={"email": "student@techniview.local"}
    )

    def fail(_message, _id):
        raise httpx.ConnectError("sensitive provider content")

    monkeypatch.setattr(email_delivery, "_deliver", fail)
    monkeypatch.setattr(settings, "EMAIL_MAX_ATTEMPTS", 2)
    assert process_email_jobs(db_session) == 1
    job = db_session.scalar(select(EmailJob))
    assert job.last_error == "ConnectError"
    assert job.sent_at is None
    assert process_email_jobs(db_session) == 0
    job.available_at = now_utc() - timedelta(seconds=1)
    db_session.commit()
    assert process_email_jobs(db_session) == 1
    job.available_at = now_utc() - timedelta(seconds=1)
    db_session.commit()
    assert process_email_jobs(db_session) == 0
    assert job.attempts == 2


async def test_expired_verification_and_archived_course_cannot_enroll(
    client, teacher_client, db_session
):
    from app.seed import DEMO_COURSE_JOIN_TOKEN

    response = await client.post(
        f"/api/join/{DEMO_COURSE_JOIN_TOKEN}/signup",
        json={
            "name": "Pending",
            "email": "pending@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert response.status_code == 202
    token = db_session.scalar(select(AccountToken))
    token.expires_at = now_utc() - timedelta(seconds=1)
    db_session.commit()
    assert (
        await client.post(
            "/api/auth/verify-email", json={"token": account_token_value(token)}
        )
    ).status_code == 400
    token.expires_at = now_utc() + timedelta(hours=1)
    db_session.commit()
    assert (await teacher_client.post("/api/courses/1/archive")).status_code == 200
    assert (
        await client.post(
            "/api/auth/verify-email", json={"token": account_token_value(token)}
        )
    ).status_code == 409
    assert (
        db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == token.user_id)
        )
        is None
    )


async def test_csv_validation_rolls_back_rows_before_invalid_account(
    teacher_client, db_session
):
    response = await teacher_client.post(
        "/api/courses/1/enrollments/import",
        json={
            "csv": "name,email\nNew,new@example.com\nTeacher,teacher@techniview.local\n"
        },
    )
    assert response.status_code == 422
    assert db_session.scalar(select(CourseEnrollment)) is None
    assert db_session.scalar(select(EmailJob)) is None


async def test_password_recovery_cooldown_and_ip_throttle(
    client, db_session, monkeypatch
):
    from app.services import account_throttle

    monkeypatch.setattr(account_throttle, "ACCOUNT_REQUESTS_PER_HOUR", 2)
    for _ in range(2):
        assert (
            await client.post(
                "/api/auth/password-recovery",
                json={"email": "student@techniview.local"},
            )
        ).status_code == 202
    assert len(db_session.scalars(select(AccountToken)).all()) == 1
    assert (
        await client.post(
            "/api/auth/password-recovery", json={"email": "unknown@example.com"}
        )
    ).status_code == 429


async def test_email_job_recovers_expired_claim(client, db_session, tmp_path):
    await client.post(
        "/api/auth/password-recovery", json={"email": "student@techniview.local"}
    )
    job = db_session.scalar(select(EmailJob))
    job.claimed_by = "crashed-worker"
    job.claimed_at = now_utc() - timedelta(seconds=settings.EMAIL_LEASE_SECONDS + 1)
    db_session.commit()
    assert process_email_jobs(db_session) == 1
    assert job.claimed_by is None
    assert job.sent_at is not None
    assert len(list(tmp_path.glob("*.json"))) == 1
