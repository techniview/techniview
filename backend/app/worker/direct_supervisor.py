"""Own separate execution-worker processes; each owns its database sessions."""

import os
import signal
import subprocess
import sys
import time


def main():
    count = int(os.getenv("DIRECT_WORKER_PROCESSES", "4"))
    if not 1 <= count <= 16:
        raise ValueError("DIRECT_WORKER_PROCESSES must be between 1 and 16")
    children = []
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    failed = False
    try:
        for _ in range(count):
            if stopping:
                break
            children.append(subprocess.Popen([sys.executable, "-m", "app.worker"]))
        while not stopping:
            if any(child.poll() is not None for child in children):
                failed = True
                break
            time.sleep(0.2)
    finally:
        stop(None, None)
        deadline = time.monotonic() + 20
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
