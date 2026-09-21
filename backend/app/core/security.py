import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, UserSession
from .config import settings
from .db import get_db
from .errors import ApiError

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(digest.hex(), expected)
    except ValueError, TypeError:
        return False


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def create_session(db: Session, user: User) -> tuple[str, UserSession]:
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC).replace(tzinfo=None)
    session = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.SESSION_DAYS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session_token: Annotated[
        str | None, Cookie(alias=settings.SESSION_COOKIE_NAME)
    ] = None,
) -> User:
    if not session_token:
        raise ApiError(401, "authentication_required", "Authentication is required.")

    now = datetime.now(UTC).replace(tzinfo=None)
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(session_token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    if session is None:
        raise ApiError(401, "invalid_session", "The session is invalid or expired.")

    user = db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        raise ApiError(401, "invalid_session", "The session is invalid or expired.")

    session.last_used_at = now
    db.commit()
    return user
