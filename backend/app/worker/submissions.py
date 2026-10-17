import logging
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import or_, select

from ..core.config import settings
from ..core.judge0 import judge0_get, judge0_submit
from ..core.observability import log_event
from ..core.security import hash_token
from ..models import Submission, SubmissionStatus
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
    # Use SKIP LOCKED only on this scheduling read, then acquire domain locks in order.
    candidates = list(db.scalars(query.limit(20)).all())
    db.commit()
    for candidate in candidates:
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


def process_submission(db, submission_id: int, owner: str) -> None:
    row = results._load_submission(db, submission_id)
    if row is None or row.claim_owner != owner:
        db.rollback()
        return
    log_event(logger, logging.INFO, "submission_claimed", submission_id=submission_id)
    case_ids = [r.test_case_id for r in row.case_results]
    db.commit()
    for case_id in case_ids:
        row = results._load_submission(db, submission_id)
        if (
            row is None
            or row.claim_owner != owner
            or row.status in results.TERMINAL_SUBMISSION_STATUSES
        ):
            db.rollback()
            return
        case = next(r for r in row.case_results if r.test_case_id == case_id)
        if results._is_terminal(case.judge0_status_id):
            db.commit()
            continue
        now = utc_now()
        row.claimed_at = now
        token = case.judge0_token
        start = case.dispatch_started_at
        dispatch = start is None and token is None
        callback = None
        if dispatch:
            callback = secrets.token_urlsafe(32)
            case.callback_token_hash = hash_token(callback)
            case.dispatch_started_at = now
        expired = start is not None and now - start >= timedelta(
            seconds=settings.WORKER_RECOVERY_SECONDS
        )
        cpu = float(case.cpu_time_limit_seconds)
        memory = case.memory_limit_kb
        db.commit()
        report = None
        failed = False
        try:
            if dispatch:
                report = judge0_submit(
                    case.execution_source,
                    stdin=case.execution_stdin,
                    expected_output=case.execution_expected_output,
                    wait=False,
                    timeout=5,
                    callback_url=f"{settings.JUDGE0_CALLBACK_BASE_URL}/{callback}",
                    cpu_time_limit=cpu,
                    memory_limit=memory,
                )
                token = report["token"]
                if not isinstance(token, str) or not token or len(token) > 36:
                    raise ValueError("invalid Judge0 token")
                log_event(
                    logger,
                    logging.INFO,
                    "case_dispatched_to_judge0",
                    submission_id=submission_id,
                )
            elif token is not None:
                report = judge0_get(token)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ArithmeticError):
            # No resend after an ambiguous network error. Callback may still recover it.
            failed = True
            log_event(
                logger,
                logging.WARNING,
                "judge0_request_failed",
                submission_id=submission_id,
            )
        row = results._load_submission(db, submission_id)
        if (
            row is None
            or row.claim_owner != owner
            or row.status in results.TERMINAL_SUBMISSION_STATUSES
        ):
            db.rollback()
            return
        case = next(r for r in row.case_results if r.test_case_id == case_id)
        if not results._is_terminal(case.judge0_status_id):
            if token is not None:
                case.judge0_token = token
            if report is not None and not failed:
                try:
                    results._update_case_result(case, report)
                except (TypeError, ValueError, ArithmeticError):
                    failed = True
            if expired and (failed or not results._is_terminal(case.judge0_status_id)):
                case.infrastructure_error = True
                case.judge0_status_id = results.Judge0Status.INTERNAL_ERROR
        results._finalize_submission(db, row)
        db.commit()
    row = results._load_submission(db, submission_id)
    if row is not None and row.claim_owner == owner:
        results._finalize_submission(db, row)
        row.claim_owner = None
        row.claimed_at = None
        row.next_check_at = utc_now() + timedelta(seconds=settings.WORKER_POLL_SECONDS)
        db.commit()
        if row.status in results.TERMINAL_SUBMISSION_STATUSES:
            log_event(
                logger,
                logging.INFO,
                "submission_completed",
                submission_id=submission_id,
                status=row.status.value,
            )
    else:
        db.rollback()


def process_next_submission(db, owner: str) -> bool:
    submission_id = claim_submission(db, owner)
    if submission_id is None:
        return False
    process_submission(db, submission_id, owner)
    return True
