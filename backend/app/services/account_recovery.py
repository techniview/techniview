import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from ..core.authorization import require_active_course
from ..core.config import settings
from ..core.errors import ApiError
from ..core.security import hash_password, hash_token
from ..models import AccountToken, EmailJob, User, UserSession


def now_utc():
    return datetime.now(UTC).replace(tzinfo=None)


def require_email_delivery() -> None:
    if (
        settings.EMAIL_DELIVERY_MODE not in {"capture", "resend"}
        or len(settings.EMAIL_SIGNING_KEY) < 32
    ):
        raise ApiError(503, "email_unavailable", "Email delivery is not configured.")
    if settings.EMAIL_DELIVERY_MODE == "resend" and (
        not settings.RESEND_API_KEY or not settings.EMAIL_FROM
    ):
        raise ApiError(503, "email_unavailable", "Email delivery is not configured.")


def signed_secret(context: str) -> str:
    return hmac.new(
        settings.EMAIL_SIGNING_KEY.encode(), context.encode(), hashlib.sha256
    ).hexdigest()


def account_token_value(token: AccountToken) -> str:
    return signed_secret(f"account:{token.purpose}:{token.nonce}")


def issue_account_token(
    db, user: User, purpose: str, course_id: int | None = None
) -> None:
    require_email_delivery()
    now = now_utc()
    latest = db.scalar(
        select(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.course_id == course_id,
            AccountToken.created_at
            > now - timedelta(seconds=settings.EMAIL_TOKEN_COOLDOWN_SECONDS),
        )
        .limit(1)
    )
    if latest is not None:
        return
    minutes = (
        settings.PASSWORD_RESET_MINUTES
        if purpose == "reset"
        else settings.EMAIL_VERIFICATION_MINUTES
    )
    token = AccountToken(
        user_id=user.id,
        course_id=course_id,
        purpose=purpose,
        nonce=secrets.token_hex(32),
        created_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )
    token.token_hash = hash_token(account_token_value(token))
    db.add(token)
    db.flush()
    db.add(
        EmailJob(
            recipient=user.email,
            kind=purpose,
            user_id=user.id,
            course_id=course_id,
            token_id=token.id,
            available_at=now,
        )
    )


def request_password_reset(db, email: str) -> None:
    require_email_delivery()
    user = db.scalar(
        select(User).where(User.email == email.strip().lower()).with_for_update()
    )
    if user is not None and user.disabled_at is None:
        issue_account_token(db, user, "reset")
    db.commit()


def _usable_token(db, token: str, purpose: str):
    candidate = db.scalar(
        select(AccountToken).where(
            AccountToken.token_hash == hash_token(token),
            AccountToken.purpose == purpose,
        )
    )
    if candidate is None:
        raise ApiError(400, "invalid_token", "This link is invalid or expired.")
    # Course before user matches the join and enrollment lock order.
    if candidate.course_id is not None:
        require_active_course(db, candidate.course_id)
    user = db.scalar(
        select(User)
        .where(User.id == candidate.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = db.scalar(
        select(AccountToken)
        .where(AccountToken.id == candidate.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.disabled_at is not None
        or record.used_at is not None
        or record.expires_at <= now_utc()
    ):
        raise ApiError(400, "invalid_token", "This link is invalid or expired.")
    return user, record


def reset_password(db, token: str, password: str) -> None:
    user, _record = _usable_token(db, token, "reset")
    now = now_utc()
    user.password_hash = hash_password(password)
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_id == user.id,
            AccountToken.purpose == "reset",
            AccountToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()


def verify_email(db, token: str) -> User:
    from .enrollment import enroll_student

    user, record = _usable_token(db, token, "verify")
    user.email_verified_at = user.email_verified_at or now_utc()
    record.used_at = now_utc()
    if record.course_id is not None:
        enroll_student(db, record.course_id, user)
    db.commit()
    return user
