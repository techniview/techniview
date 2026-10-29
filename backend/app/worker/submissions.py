import hashlib
import hmac
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy import or_, select

from ..core.config import settings
from ..core.judge0 import (
    judge0_get,
    judge0_group_by_key,
    judge0_group_submit,
    judge0_submit,
)
from ..core.observability import log_event
from ..core.security import hash_token
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


def _retry_delay(attempt: int, retry_after: str | None = None) -> float:
    base = settings.WORKER_RETRY_BASE_SECONDS
    delay = min(base * (2 ** max(0, attempt - 1)), settings.WORKER_RETRY_MAX_SECONDS)
    jitter = 0.75 + secrets.randbelow(501) / 1000
    delay *= jitter
    if retry_after:
        try:
            delay = max(delay, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delay = max(delay, (retry_at - datetime.now(UTC)).total_seconds())
            except TypeError, ValueError, OverflowError:
                pass
    return max(0.0, min(delay, settings.WORKER_RETRY_AFTER_MAX_SECONDS))


def _schedule_case(row, case, now: datetime, delay: float) -> None:
    case.next_attempt_at = now + timedelta(seconds=delay)
    row.next_check_at = (
        case.next_attempt_at
        if row.next_check_at is None
        else min(row.next_check_at, case.next_attempt_at)
    )


def _schedule_submission(row, now: datetime) -> None:
    outstanding = [
        case.next_attempt_at
        for case in row.case_results
        if not results._is_terminal(case.judge0_status_id)
    ]
    if any(next_attempt is None for next_attempt in outstanding):
        row.next_check_at = now
    elif outstanding:
        row.next_check_at = min(outstanding)
    else:
        row.next_check_at = None


def _is_retryable_poll_error(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code if error.response else None
        return status == 429 or (status is not None and status >= 500)
    return isinstance(error, httpx.HTTPError)


def _mark_infrastructure_failure(row, case, failure_code: str) -> None:
    case.infrastructure_error = True
    case.judge0_status_id = results.Judge0Status.INTERNAL_ERROR
    row.failure_code = failure_code


def _group_key(row: Submission) -> str:
    material = f"group:{row.id}:{row.submitted_at.isoformat(timespec='microseconds')}"
    return hmac.new(
        settings.RUNNER_GROUP_SECRET.encode(), material.encode(), hashlib.sha256
    ).hexdigest()


def _group_callback(key: str, case_id: int) -> str:
    return hmac.new(
        settings.RUNNER_GROUP_SECRET.encode(),
        f"callback:{key}:{case_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _release_group_claim(db, row: Submission, now: datetime) -> None:
    results._finalize_submission(db, row)
    _schedule_submission(row, now)
    row.claim_owner = None
    row.claimed_at = None
    db.commit()


def _process_group_submission(db, submission_id: int, owner: str) -> None:
    row = results._load_submission(db, submission_id)
    if row is None or row.claim_owner != owner:
        db.rollback()
        return
    ordered_cases = sorted(row.case_results, key=lambda case: case.case_order)
    case_ids = [case.test_case_id for case in ordered_cases]
    missing = [
        case
        for case in row.case_results
        if case.judge0_token is None and not results._is_terminal(case.judge0_status_id)
    ]
    if not missing:
        db.commit()
        process_submission(db, submission_id, owner, case_ids_override=case_ids)
        return

    key = _group_key(row)
    first_attempt = all(case.dispatch_started_at is None for case in missing)
    now = utc_now()
    payload = []
    for case in ordered_cases:
        callback = _group_callback(key, case.test_case_id)
        callback_hash = hash_token(callback)
        if (
            case.callback_token_hash is not None
            and case.callback_token_hash != callback_hash
        ):
            raise ValueError("group callback token changed during recovery")
        case.callback_token_hash = callback_hash
        if case.dispatch_started_at is None:
            case.dispatch_started_at = now
        payload.append(
            {
                "case_id": case.test_case_id,
                "source_code": case.execution_source,
                "stdin": case.execution_stdin,
                "expected_output": case.execution_expected_output,
                "callback_url": f"{settings.JUDGE0_CALLBACK_BASE_URL}/{callback}",
                "cpu_time_limit": float(case.cpu_time_limit_seconds),
                "memory_limit": case.memory_limit_kb,
            }
        )
    row.claimed_at = now
    db.commit()

    report = None
    failure = None
    started = time.perf_counter()
    try:
        if not first_attempt:
            try:
                report = judge0_group_by_key(key)
            except httpx.HTTPStatusError as error:
                if error.response is None or error.response.status_code != 404:
                    raise
        if report is None:
            report = judge0_group_submit(key, payload)
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        failure = error
    log_event(
        logger,
        logging.INFO,
        "runner_group_request_completed",
        submission_id=submission_id,
        seconds=time.perf_counter() - started,
        failed=failure is not None,
    )

    row = results._load_submission(db, submission_id)
    if row is None or row.claim_owner != owner:
        db.rollback()
        return
    now = utc_now()
    if failure is not None:
        status = (
            failure.response.status_code
            if isinstance(failure, httpx.HTTPStatusError) and failure.response
            else None
        )
        expired = any(
            case.dispatch_started_at
            and now - case.dispatch_started_at
            >= timedelta(seconds=settings.WORKER_RECOVERY_SECONDS)
            for case in row.case_results
        )
        if expired or (status is not None and status in {400, 409, 422}):
            for case in row.case_results:
                if not results._is_terminal(case.judge0_status_id):
                    _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
        else:
            for case in row.case_results:
                if case.judge0_token is None:
                    case.next_attempt_at = now + timedelta(seconds=5)
        _release_group_claim(db, row, now)
        return

    try:
        returned = report["cases"]
        if not isinstance(returned, list) or len(returned) != len(case_ids):
            raise ValueError("group case count mismatch")
        tokens = {}
        for item in returned:
            case_id, token = item["case_id"], item["token"]
            if (
                not isinstance(case_id, int)
                or case_id in tokens
                or not isinstance(token, str)
                or not token
                or len(token) > 36
            ):
                raise ValueError("invalid group case identity")
            tokens[case_id] = token
        if set(tokens) != set(case_ids):
            raise ValueError("group case identities mismatch")
        for case in row.case_results:
            token = tokens[case.test_case_id]
            if case.judge0_token is not None and case.judge0_token != token:
                raise ValueError("group case token changed")
            case.judge0_token = token
            case.next_attempt_at = None
    except KeyError, TypeError, ValueError:
        for case in row.case_results:
            if not results._is_terminal(case.judge0_status_id):
                _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
        _release_group_claim(db, row, now)
        return
    db.commit()
    process_submission(db, submission_id, owner, case_ids_override=case_ids)


def process_submission(
    db,
    submission_id: int,
    owner: str,
    *,
    case_ids_override: list[int] | None = None,
) -> None:
    if case_ids_override is None and settings.RUNNER_GROUP_PROFILE:
        _process_group_submission(db, submission_id, owner)
        return
    row = results._load_submission(db, submission_id)
    if row is None or row.claim_owner != owner:
        db.rollback()
        return
    log_event(logger, logging.INFO, "submission_claimed", submission_id=submission_id)
    case_ids = (
        case_ids_override
        if case_ids_override is not None
        else [result.test_case_id for result in row.case_results]
    )
    row.next_check_at = None
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
        case = next(
            result for result in row.case_results if result.test_case_id == case_id
        )
        if results._is_terminal(case.judge0_status_id):
            db.commit()
            continue

        now = utc_now()
        if case.next_attempt_at and case.next_attempt_at > now:
            db.commit()
            continue

        token = case.judge0_token
        start = case.dispatch_started_at
        dispatch = start is None and token is None
        callback = None
        if dispatch:
            callback = secrets.token_urlsafe(32)
            case.callback_token_hash = hash_token(callback)
            case.dispatch_started_at = now
            case.dispatch_attempt_count += 1
        expired = start is not None and now - start >= timedelta(
            seconds=settings.WORKER_RECOVERY_SECONDS
        )
        cpu = float(case.cpu_time_limit_seconds)
        memory = case.memory_limit_kb
        row.claimed_at = now
        db.commit()

        report = None
        failure: Exception | None = None
        request_started = time.perf_counter()
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
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            ArithmeticError,
        ) as error:
            failure = error

        log_event(
            logger,
            logging.INFO,
            "runner_request_completed",
            submission_id=submission_id,
            case_id=case_id,
            operation="dispatch" if dispatch else "poll",
            seconds=time.perf_counter() - request_started,
            failed=failure is not None,
        )
        row = results._load_submission(db, submission_id)
        if (
            row is None
            or row.claim_owner != owner
            or row.status in results.TERMINAL_SUBMISSION_STATUSES
        ):
            db.rollback()
            return
        case = next(
            result for result in row.case_results if result.test_case_id == case_id
        )
        now = utc_now()

        if dispatch and isinstance(failure, httpx.HTTPStatusError):
            status = failure.response.status_code if failure.response else None
            if status == 429:
                case.callback_token_hash = None
                case.dispatch_started_at = None
                if case.dispatch_attempt_count <= settings.WORKER_DISPATCH_MAX_RETRIES:
                    _schedule_case(
                        row,
                        case,
                        now,
                        _retry_delay(
                            case.dispatch_attempt_count,
                            failure.response.headers.get("Retry-After")
                            if failure.response
                            else None,
                        ),
                    )
                    log_event(
                        logger,
                        logging.WARNING,
                        "judge0_dispatch_rejected_busy",
                        submission_id=submission_id,
                        attempt=case.dispatch_attempt_count,
                    )
                else:
                    _mark_infrastructure_failure(row, case, "runner_busy")
                    log_event(
                        logger,
                        logging.ERROR,
                        "judge0_dispatch_busy_retries_exhausted",
                        submission_id=submission_id,
                        attempts=case.dispatch_attempt_count,
                    )
            elif status is not None and 400 <= status < 500:
                _mark_infrastructure_failure(row, case, "runner_rejected")
                log_event(
                    logger,
                    logging.ERROR,
                    "judge0_dispatch_rejected",
                    submission_id=submission_id,
                    status=status,
                )
            else:
                log_event(
                    logger,
                    logging.WARNING,
                    "judge0_dispatch_outcome_ambiguous",
                    submission_id=submission_id,
                )
        elif (
            failure is not None
            and token is not None
            and _is_retryable_poll_error(failure)
        ):
            case.poll_failure_count += 1
            if expired:
                _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
            else:
                retry_after = None
                if isinstance(failure, httpx.HTTPStatusError) and failure.response:
                    retry_after = failure.response.headers.get("Retry-After")
                _schedule_case(
                    row,
                    case,
                    now,
                    _retry_delay(case.poll_failure_count, retry_after),
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "judge0_poll_failed_retrying",
                    submission_id=submission_id,
                    failure_count=case.poll_failure_count,
                )
        elif failure is not None:
            log_event(
                logger,
                logging.WARNING,
                "judge0_request_failed",
                submission_id=submission_id,
            )
            if expired:
                _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
            elif not dispatch:
                case.poll_failure_count += 1
                _schedule_case(
                    row,
                    case,
                    now,
                    _retry_delay(case.poll_failure_count),
                )
            else:
                _schedule_case(
                    row,
                    case,
                    now,
                    max(
                        0.0,
                        (
                            case.dispatch_started_at
                            + timedelta(seconds=settings.WORKER_RECOVERY_SECONDS)
                            - now
                        ).total_seconds(),
                    ),
                )
        elif report is not None:
            if token is not None:
                case.judge0_token = token
            try:
                reported_failure_code = results._update_case_result(case, report)
            except TypeError, ValueError, ArithmeticError:
                if expired:
                    _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
                else:
                    case.poll_failure_count += 1
                    _schedule_case(
                        row,
                        case,
                        now,
                        _retry_delay(case.poll_failure_count),
                    )
            else:
                case.poll_failure_count = 0
                if results._is_terminal(case.judge0_status_id):
                    case.next_attempt_at = None
                    if reported_failure_code is not None:
                        row.failure_code = reported_failure_code
                    elif case.infrastructure_error:
                        row.failure_code = row.failure_code or "runner_internal_error"
                elif case.judge0_token is not None:
                    _schedule_case(row, case, now, settings.WORKER_POLL_SECONDS)
                elif case.dispatch_started_at is not None:
                    recovery_at = case.dispatch_started_at + timedelta(
                        seconds=settings.WORKER_RECOVERY_SECONDS
                    )
                    _schedule_case(
                        row,
                        case,
                        now,
                        max(0.0, (recovery_at - now).total_seconds()),
                    )
        elif dispatch:
            case.judge0_token = token
            case.next_attempt_at = now + timedelta(seconds=settings.WORKER_POLL_SECONDS)

        if expired and not results._is_terminal(case.judge0_status_id):
            _mark_infrastructure_failure(row, case, "runner_outcome_unknown")
        results._finalize_submission(db, row)
        db.commit()

    row = results._load_submission(db, submission_id)
    if row is not None and row.claim_owner == owner:
        results._finalize_submission(db, row)
        _schedule_submission(row, utc_now())
        row.claim_owner = None
        row.claimed_at = None
        db.commit()
        if row.status in results.TERMINAL_SUBMISSION_STATUSES:
            log_event(
                logger,
                logging.INFO,
                "submission_completed",
                submission_id=submission_id,
                status=row.status.value,
                failure_code=row.failure_code,
            )
    else:
        db.rollback()


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
