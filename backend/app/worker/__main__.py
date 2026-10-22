import logging
import secrets
import signal
import time

from ..core.db import SessionLocal
from ..core.observability import configure_logging, log_event
from ..services.email_delivery import process_email_jobs
from .submissions import process_next_submission, purge_expired_idempotency_keys

logger = logging.getLogger("techniview.worker")


def main():
    logging.basicConfig(level=logging.INFO)
    configure_logging()
    owner = secrets.token_hex(16)
    stopping = False
    next_idempotency_cleanup = time.monotonic()

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        try:
            with SessionLocal() as db:
                worked = process_next_submission(db, owner)
            with SessionLocal() as db:
                process_email_jobs(db, limit=5)
            if time.monotonic() >= next_idempotency_cleanup:
                with SessionLocal() as db:
                    purged = purge_expired_idempotency_keys(db)
                if purged:
                    log_event(
                        logger,
                        logging.INFO,
                        "expired_idempotency_keys_purged",
                        count=purged,
                    )
                next_idempotency_cleanup = time.monotonic() + 3600
        except Exception:
            # Avoid exception text: HTTP failures can include callback credentials.
            log_event(logger, logging.ERROR, "worker_job_failed_recoverable")
            worked = False
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
