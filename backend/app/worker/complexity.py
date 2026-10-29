"""Run advisory complexity estimates independently from grading workers."""

import logging
import signal
import time

from ..core.config import settings
from ..core.db import SessionLocal
from ..core.observability import configure_logging, log_event
from ..services.complexity_analysis import process_next_analysis

logger = logging.getLogger("techniview.complexity_worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    configure_logging()
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    if not settings.BIG_O_OLLAMA_URL:
        log_event(logger, logging.INFO, "complexity_worker_disabled")
    while not stopping:
        try:
            with SessionLocal() as db:
                worked = process_next_analysis(db)
        except Exception:
            # The code and model endpoint response can contain student data.
            log_event(logger, logging.ERROR, "complexity_analysis_failed_recoverable")
            worked = False
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
