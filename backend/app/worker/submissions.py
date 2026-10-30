import logging
from datetime import timedelta

from sqlalchemy import or_, select

from ..core.config import settings
from ..models import (
    Submission,
    SubmissionIdempotencyKey,
    SubmissionStatus,
)
from ..routers import submissions as results
from ..services.progress import utc_now

logger = logging.getLogger("techniview.worker")


def claim_submission(db, owner: str, submission_id: int | None = None):
    now = utc_now()
    query = (
        select(Submission.id)
        .where(
            Submission.status.in_((SubmissionStatus.QUEUED, SubmissionStatus.RUNNING)),
            or_(
                Submission.claimed_at.is_(None),
                Submission.claimed_at
                < now - timedelta(seconds=settings.WORKER_LEASE_SECONDS),
            ),
            or_(Submission.next_check_at.is_(None), Submission.next_check_at <= now),
        )
        .order_by(Submission.id)
    )
    if submission_id is not None:
        query = query.where(Submission.id == submission_id)
    candidates = list(db.scalars(query.limit(20)).all())
    db.commit()
    for candidate in candidates:
        # This locking read is the claim's compare-and-set. Course locking comes
        # first because callback and assignment mutations use the same lock order.
        row = results._load_submission(db, candidate)
        if row is None or row.status in results.TERMINAL_SUBMISSION_STATUSES:
            db.rollback()
            continue
        if row.claimed_at and row.claimed_at >= now - timedelta(
            seconds=settings.WORKER_LEASE_SECONDS
        ):
            db.rollback()
            continue
        if row.next_check_at and row.next_check_at > now:
            db.rollback()
            continue
        row.claim_owner = owner
        row.claimed_at = now
        db.commit()
        return candidate
    return None


def _mark_infrastructure_failure(row, case, failure_code: str) -> None:
    case.infrastructure_error = True
    case.judge0_status_id = results.ExecutionStatus.INTERNAL_ERROR
    row.failure_code = failure_code


def process_submission(db, submission_id: int, owner: str) -> None:
    from .direct import process_submission as process_direct

    process_direct(db, submission_id, owner)


def purge_expired_idempotency_keys(db, limit: int = 500) -> int:
    expired = list(
        db.scalars(
            select(SubmissionIdempotencyKey)
            .where(SubmissionIdempotencyKey.expires_at <= utc_now())
            .order_by(SubmissionIdempotencyKey.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for record in expired:
        db.delete(record)
    db.commit()
    return len(expired)


def process_next_submission(db, owner: str) -> bool:
    submission_id = claim_submission(db, owner)
    if submission_id is None:
        return False
    process_submission(db, submission_id, owner)
    return True
