import csv
import io
import re
from datetime import timedelta

from sqlalchemy import or_, select

from ..core.config import settings
from ..core.errors import ApiError
from ..core.security import hash_token
from ..models import (
    CourseEnrollment,
    CourseMembership,
    EmailJob,
    MembershipRole,
    User,
    UserRole,
)
from .account_recovery import now_utc, require_email_delivery
from .email_delivery import enrollment_token_value

MAX_ENROLLMENT_ROWS = 2000
EMAIL_PATTERN = re.compile(r"^[^\s@,]+@[^\s@,]+\.[^\s@,]+$")


def parse_enrollment_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), strict=True)
    if reader.fieldnames != ["name", "email"]:
        raise ApiError(422, "invalid_csv", "CSV must have name,email headers.")
    entries = {}
    try:
        for row in reader:
            if len(entries) >= MAX_ENROLLMENT_ROWS:
                raise ApiError(422, "invalid_csv", "CSV exceeds 2000 students.")
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            if (
                None in row
                or not name
                or len(name) > 100
                or len(email) > 255
                or not EMAIL_PATTERN.fullmatch(email)
            ):
                raise ApiError(
                    422,
                    "invalid_csv",
                    "CSV contains an invalid name or email.",
                    {"line": reader.line_num},
                )
            if email in entries:
                raise ApiError(
                    422,
                    "duplicate_email",
                    "CSV contains a duplicate email.",
                    {"line": reader.line_num},
                )
            entries[email] = {"name": name, "email": email}
    except csv.Error as exc:
        raise ApiError(422, "invalid_csv", "CSV is malformed.") from exc
    if not entries:
        raise ApiError(422, "invalid_csv", "CSV contains no students.")
    return list(entries.values())


def enroll_student(db, course_id: int, user: User) -> CourseMembership:
    if user.email_verified_at is None:
        raise ApiError(
            403, "email_unverified", "Verify your email before joining a class."
        )
    membership = db.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course_id, CourseMembership.user_id == user.id
        )
    )
    if membership is None:
        membership = CourseMembership(
            course_id=course_id, user_id=user.id, role=MembershipRole.STUDENT
        )
        db.add(membership)
    else:
        membership.withdrawn_at = None
    pending = db.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.email == user.email,
        )
    )
    if pending is not None:
        db.delete(pending)
    db.flush()
    return membership


def import_enrollment_csv(db, course_id: int, content: str) -> dict[str, int]:
    entries = parse_enrollment_csv(content)
    require_email_delivery()
    with db.begin_nested():
        return _import_entries(db, course_id, entries)


def _import_entries(db, course_id, entries):
    enrolled = pending_count = 0
    for entry in entries:
        user = db.scalar(select(User).where(User.email == entry["email"]))
        if user is not None:
            if user.disabled_at is not None or user.role != UserRole.STUDENT:
                raise ApiError(
                    422,
                    "invalid_enrollment",
                    "CSV includes an unavailable student account.",
                    {"email": entry["email"]},
                )
            membership = db.scalar(
                select(CourseMembership).where(
                    CourseMembership.course_id == course_id,
                    CourseMembership.user_id == user.id,
                )
            )
            if membership is not None and membership.role != MembershipRole.STUDENT:
                raise ApiError(
                    422,
                    "invalid_enrollment",
                    "CSV includes a course staff member.",
                    {"email": entry["email"]},
                )
            if user.email_verified_at is not None:
                newly_enrolled = (
                    membership is None or membership.withdrawn_at is not None
                )
                enroll_student(db, course_id, user)
                if newly_enrolled:
                    db.add(
                        EmailJob(
                            recipient=user.email,
                            kind="enrolled",
                            user_id=user.id,
                            course_id=course_id,
                            available_at=now_utc(),
                        )
                    )
                enrolled += 1
            else:
                _queue_pending(db, course_id, entry)
                pending_count += 1
        else:
            _queue_pending(db, course_id, entry)
            pending_count += 1
    return {"enrolled": enrolled, "pending_signup": pending_count}


def _queue_pending(db, course_id: int, entry: dict[str, str]) -> None:
    pending = db.scalar(
        select(CourseEnrollment)
        .where(
            CourseEnrollment.course_id == course_id,
            CourseEnrollment.email == entry["email"],
        )
        .with_for_update()
    )
    if pending is not None:
        pending.name = entry["name"]
        active_job = db.scalar(
            select(EmailJob.id)
            .where(
                EmailJob.enrollment_id == pending.id,
                EmailJob.kind == "enrollment",
                EmailJob.sent_at.is_(None),
                or_(
                    EmailJob.attempts < settings.EMAIL_MAX_ATTEMPTS,
                    EmailJob.claimed_at
                    >= now_utc() - timedelta(seconds=settings.EMAIL_LEASE_SECONDS),
                ),
            )
            .limit(1)
        )
        if active_job is None:
            _queue_enrollment_email(db, pending)
        return
    pending = CourseEnrollment(course_id=course_id, **entry)
    db.add(pending)
    db.flush()
    pending.token_hash = hash_token(enrollment_token_value(pending))
    _queue_enrollment_email(db, pending)


def _queue_enrollment_email(db, pending: CourseEnrollment) -> None:
    db.add(
        EmailJob(
            recipient=pending.email,
            kind="enrollment",
            course_id=pending.course_id,
            enrollment_id=pending.id,
            available_at=now_utc(),
        )
    )
