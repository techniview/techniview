import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..core.errors import ApiError
from ..models import AccountRequestThrottle
from .account_recovery import now_utc

ACCOUNT_REQUESTS_PER_HOUR = 30


def throttle_account_request(db, action: str, address: str) -> None:
    key = hashlib.sha256(f"{action}:{address}".encode()).hexdigest()
    now = now_utc()
    row = db.scalar(
        select(AccountRequestThrottle)
        .where(AccountRequestThrottle.key == key)
        .with_for_update()
    )
    if row is None:
        try:
            with db.begin_nested():
                row = AccountRequestThrottle(
                    key=key, window_started_at=now, request_count=0
                )
                db.add(row)
                db.flush()
        except IntegrityError:
            row = db.scalar(
                select(AccountRequestThrottle)
                .where(AccountRequestThrottle.key == key)
                .with_for_update()
            )
    if row.window_started_at <= now - timedelta(hours=1):
        row.window_started_at = now
        row.request_count = 0
    if row.request_count >= ACCOUNT_REQUESTS_PER_HOUR:
        db.commit()
        raise ApiError(
            429, "rate_limited", "Too many account requests. Try again later."
        )
    row.request_count += 1
    db.commit()
