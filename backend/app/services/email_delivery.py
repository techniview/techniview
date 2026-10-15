import json
import os
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import or_, select

from ..core.config import settings
from ..models import (
    AccountToken,
    Course,
    CourseEnrollment,
    CourseMembership,
    EmailJob,
    MembershipRole,
)
from .account_recovery import account_token_value, now_utc, signed_secret


def enrollment_token_value(enrollment: CourseEnrollment) -> str:
    return signed_secret(f"enrollment:{enrollment.id}:{enrollment.email}")


def _message(db, job: EmailJob) -> dict[str, object] | None:
    if job.kind == "enrolled":
        course = db.get(Course, job.course_id)
        membership = db.scalar(
            select(CourseMembership).where(
                CourseMembership.course_id == job.course_id,
                CourseMembership.user_id == job.user_id,
                CourseMembership.role == MembershipRole.STUDENT,
                CourseMembership.withdrawn_at.is_(None),
            )
        )
        if course is None or course.archived_at is not None or membership is None:
            return None
        url = settings.PUBLIC_APP_URL.rstrip("/") + f"/student/courses/{course.id}"
        subject = f"You joined {course.name} on TechniView"
        content = f"Your instructor added you to {course.name}. Open the class: {url}"
    elif job.kind == "enrollment":
        enrollment = db.get(CourseEnrollment, job.enrollment_id)
        course = db.get(Course, job.course_id)
        if enrollment is None or course is None or course.archived_at is not None:
            return None
        url = (
            settings.PUBLIC_APP_URL.rstrip("/")
            + "/join/"
            + enrollment_token_value(enrollment)
        )
        subject = f"Join {course.name} on TechniView"
        content = (
            f"You have been added to {course.name}. "
            f"Sign up or log in using this link: {url}"
        )
    else:
        token = db.get(AccountToken, job.token_id)
        if token is None or token.used_at is not None or token.expires_at <= now_utc():
            return None
        if token.course_id is not None:
            course = db.get(Course, token.course_id)
            if course is None or course.archived_at is not None:
                return None
        path = "/reset-password" if job.kind == "reset" else "/verify-email"
        url = (
            settings.PUBLIC_APP_URL.rstrip("/")
            + path
            + "?"
            + urlencode({"token": account_token_value(token)})
        )
        subject = (
            "Reset your TechniView password"
            if job.kind == "reset"
            else "Verify your TechniView email"
        )
        content = (
            f"{subject}: {url}\n\n"
            f"This link expires at {token.expires_at.isoformat()} UTC.\n"
            "If you did not request this, ignore this email."
        )
    return {
        "from": settings.EMAIL_FROM,
        "to": [job.recipient],
        "subject": subject,
        "text": content,
    }


def _deliver(message: dict[str, object], job_id: int) -> None:
    if settings.EMAIL_DELIVERY_MODE == "capture":
        directory = Path(settings.EMAIL_CAPTURE_DIR)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{job_id}.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump(message, output)
        return
    if settings.EMAIL_DELIVERY_MODE != "resend":
        raise RuntimeError("Email delivery is disabled")
    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Idempotency-Key": f"techniview-email-{job_id}",
        },
        json=message,
        timeout=10,
    )
    response.raise_for_status()


def process_email_jobs(db, limit: int = 20) -> int:
    processed = 0
    for _ in range(limit):
        now = now_utc()
        job = db.scalar(
            select(EmailJob)
            .where(
                EmailJob.sent_at.is_(None),
                EmailJob.attempts < settings.EMAIL_MAX_ATTEMPTS,
                EmailJob.available_at <= now,
                or_(
                    EmailJob.claimed_at.is_(None),
                    EmailJob.claimed_at
                    < now - timedelta(seconds=settings.EMAIL_LEASE_SECONDS),
                ),
            )
            .order_by(EmailJob.available_at, EmailJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            db.rollback()
            break
        claim = secrets.token_hex(16)
        job.claimed_at, job.claimed_by = now, claim
        job.attempts += 1
        job_id = job.id
        message = _message(db, job)
        db.commit()
        error = None
        try:
            if message is not None:
                _deliver(message, job_id)
        except (httpx.HTTPError, OSError, RuntimeError) as exc:
            # Store only the failure class; provider errors can include secrets.
            error = type(exc).__name__
        job = db.scalar(
            select(EmailJob)
            .where(EmailJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job.claimed_by == claim:
            job.claimed_at = job.claimed_by = None
            job.last_error = error
            if error is None:
                job.sent_at = now_utc()
            else:
                job.available_at = now_utc() + timedelta(
                    seconds=min(3600, 30 * 2 ** (job.attempts - 1))
                )
            db.commit()
        else:
            db.rollback()
        processed += 1
    return processed
