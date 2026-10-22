import hashlib
import json
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import ApiError
from ..models import Submission, SubmissionIdempotencyKey
from .progress import utc_now

IDEMPOTENCY_WINDOW = timedelta(hours=24)
_KEY_PATTERN = re.compile(r"[A-Za-z0-9._~-]{16,128}\Z")


def key_hash(key: str) -> bytes:
    if not _KEY_PATTERN.fullmatch(key):
        raise ApiError(
            422,
            "invalid_idempotency_key",
            "Idempotency-Key must be 16 to 128 URL-safe characters.",
        )
    return hashlib.sha256(key.encode("ascii")).digest()


def request_fingerprint(operation: str, payload: dict) -> bytes:
    canonical = json.dumps(
        {"operation": operation, **payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def find_existing_submission(
    db: Session,
    *,
    user_id: int,
    operation: str,
    key_digest: bytes,
    fingerprint: bytes,
) -> Submission | None:
    record = db.scalar(
        select(SubmissionIdempotencyKey)
        .where(
            SubmissionIdempotencyKey.user_id == user_id,
            SubmissionIdempotencyKey.operation == operation,
            SubmissionIdempotencyKey.key_hash == key_digest,
        )
        .with_for_update()
    )
    if record is None:
        return None
    if record.expires_at <= utc_now():
        db.delete(record)
        db.flush()
        return None
    if record.request_fingerprint != fingerprint:
        raise ApiError(
            409,
            "idempotency_key_reused",
            "This idempotency key was already used for a different request.",
        )
    return db.get(Submission, record.submission_id)


def attach_idempotency_key(
    db: Session,
    *,
    user_id: int,
    operation: str,
    key_digest: bytes,
    fingerprint: bytes,
    submission_id: int,
) -> None:
    now = utc_now()
    db.add(
        SubmissionIdempotencyKey(
            user_id=user_id,
            operation=operation,
            key_hash=key_digest,
            request_fingerprint=fingerprint,
            submission_id=submission_id,
            created_at=now,
            expires_at=now + IDEMPOTENCY_WINDOW,
        )
    )
