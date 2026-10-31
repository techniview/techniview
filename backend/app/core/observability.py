"""Small Prometheus text registry for app-level operational signals."""

import json
import logging
import os
import queue
import sqlite3
import sys
import threading
from collections import defaultdict
from contextlib import contextmanager


def configure_logging() -> None:
    logger = logging.getLogger("techniview")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


class HttpMetrics:
    duration_buckets = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)
    write_queue_capacity = 10_000
    methods = frozenset(
        {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
    )

    def __init__(self, path: str | None = None):
        self.path = path
        self._lock = threading.Lock()
        self._requests = defaultdict(int)
        self._duration_sums = defaultdict(float)
        self._duration_counts = defaultdict(int)
        self._duration_buckets = defaultdict(lambda: [0] * len(self.duration_buckets))
        self._write_queue = queue.Queue(maxsize=self.write_queue_capacity)
        self._writer_pid = None
        self._writer_thread = None
        self._pending_drops = 0
        if self.path is not None:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                bucket_columns = ", ".join(
                    f"bucket_{index} INTEGER NOT NULL DEFAULT 0"
                    for index in range(len(self.duration_buckets))
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS http_metrics ("
                    "method TEXT NOT NULL, route TEXT NOT NULL, "
                    "status INTEGER NOT NULL, "
                    "request_count INTEGER NOT NULL, duration_sum REAL NOT NULL, "
                    f"{bucket_columns}, PRIMARY KEY (method, route, status))"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS http_metrics_state ("
                    "name TEXT PRIMARY KEY, value INTEGER NOT NULL)"
                )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA synchronous = NORMAL")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def observe(self, method: str, route: str, status: int, duration: float) -> None:
        method = method if method in self.methods else "OTHER"
        key = (method, route, status)
        if self.path is not None:
            self._ensure_writer()
            try:
                self._write_queue.put_nowait((method, route, status, duration))
            except queue.Full:
                with self._lock:
                    self._pending_drops += 1
            return
        with self._lock:
            self._requests[key] += 1
            self._duration_sums[key] += duration
            self._duration_counts[key] += 1
            for index, bound in enumerate(self.duration_buckets):
                if duration <= bound:
                    self._duration_buckets[key][index] += 1

    def render(self) -> str:
        if self.path is not None:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT method, route, status, request_count, duration_sum, "
                    + ", ".join(
                        f"bucket_{i}" for i in range(len(self.duration_buckets))
                    )
                    + " FROM http_metrics"
                ).fetchall()
                dropped_observations = connection.execute(
                    "SELECT value FROM http_metrics_state "
                    "WHERE name = 'dropped_http_observations'"
                ).fetchone()
            return self._render_rows(
                rows, dropped_observations[0] if dropped_observations else 0
            )
        with self._lock:
            requests = dict(self._requests)
            duration_sums = dict(self._duration_sums)
            duration_counts = dict(self._duration_counts)
            duration_buckets = {
                key: values[:] for key, values in self._duration_buckets.items()
            }
        rows = [
            (*key, requests[key], duration_sums[key], *duration_buckets[key])
            for key in duration_counts
        ]
        return self._render_rows(rows)

    def _ensure_writer(self) -> None:
        current_pid = os.getpid()
        if self._writer_pid == current_pid and self._writer_thread.is_alive():
            return
        with self._lock:
            if self._writer_pid != current_pid:
                self._write_queue = queue.Queue(maxsize=self.write_queue_capacity)
                self._writer_pid = current_pid
            if self._writer_thread is None or not self._writer_thread.is_alive():
                self._writer_thread = threading.Thread(
                    target=self._write_loop,
                    name="techniview-http-metrics-writer",
                    daemon=True,
                )
                self._writer_thread.start()

    def _write_loop(self) -> None:
        while True:
            observation = self._write_queue.get()
            try:
                if observation is None:
                    return
                self._write_observation(*observation)
                self._flush_pending_drops()
            except Exception:
                with self._lock:
                    self._pending_drops += 1
                logging.getLogger("techniview").exception("HTTP metrics write failed")
            finally:
                self._write_queue.task_done()

    def _flush_pending_drops(self) -> None:
        with self._lock:
            dropped = self._pending_drops
            self._pending_drops = 0
        if not dropped:
            return
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO http_metrics_state (name, value) "
                    "VALUES ('dropped_http_observations', ?) "
                    "ON CONFLICT(name) DO UPDATE SET "
                    "value = value + excluded.value",
                    (dropped,),
                )
        except Exception:
            with self._lock:
                self._pending_drops += dropped
            logging.getLogger("techniview").exception(
                "HTTP metrics dropped counter write failed"
            )

    def _write_observation(
        self, method: str, route: str, status: int, duration: float
    ) -> None:
        buckets = [int(duration <= bound) for bound in self.duration_buckets]
        columns = ", ".join(f"bucket_{i}" for i in range(len(buckets)))
        values = ", ".join("?" for _ in range(5 + len(buckets)))
        updates = ", ".join(
            [
                "request_count = request_count + 1",
                "duration_sum = duration_sum + excluded.duration_sum",
            ]
            + [
                f"bucket_{i} = bucket_{i} + excluded.bucket_{i}"
                for i in range(len(buckets))
            ]
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO http_metrics "
                f"(method, route, status, request_count, duration_sum, {columns}) "
                f"VALUES ({values}) ON CONFLICT(method, route, status) "
                f"DO UPDATE SET {updates}",
                (method, route, status, 1, duration, *buckets),
            )

    def _render_rows(self, rows, dropped_observations: int = 0) -> str:
        lines = [
            "# HELP techniview_http_requests_total Completed HTTP requests.",
            "# TYPE techniview_http_requests_total counter",
        ]
        for method, route, status, count, _duration_sum, *_buckets in sorted(rows):
            labels = _labels(method=method, route=route, status=str(status))
            lines.append(f"techniview_http_requests_total{labels} {count}")
        lines.extend(
            [
                "# HELP techniview_http_request_duration_seconds HTTP duration.",
                "# TYPE techniview_http_request_duration_seconds histogram",
            ]
        )
        for method, route, status, count, duration_sum, *buckets in sorted(rows):
            for index, bound in enumerate(self.duration_buckets):
                labels = _labels(
                    method=method,
                    route=route,
                    status=str(status),
                    le=f"{bound:g}",
                )
                lines.append(
                    f"techniview_http_request_duration_seconds_bucket{labels} "
                    f"{buckets[index]}"
                )
            labels = _labels(method=method, route=route, status=str(status), le="+Inf")
            lines.append(
                f"techniview_http_request_duration_seconds_bucket{labels} {count}"
            )
            labels = _labels(method=method, route=route, status=str(status))
            lines.append(
                f"techniview_http_request_duration_seconds_count{labels} {count}"
            )
            lines.append(
                f"techniview_http_request_duration_seconds_sum{labels} "
                f"{duration_sum:.6f}"
            )
        lines.extend(
            [
                "# HELP techniview_http_metrics_dropped_total HTTP observations "
                "dropped after write queue saturation or a storage error.",
                "# TYPE techniview_http_metrics_dropped_total counter",
                f"techniview_http_metrics_dropped_total {dropped_observations}",
            ]
        )
        return "\n".join(lines) + "\n"


def _labels(**values: str) -> str:
    escaped = []
    for name, value in values.items():
        value = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        escaped.append(f'{name}="{value}"')
    return "{" + ",".join(escaped) + "}"


http_metrics = HttpMetrics(
    os.environ.get(
        "TECHNIVIEW_HTTP_METRICS_PATH", "/tmp/techniview-http-metrics.sqlite3"
    )
)


def observe_request(method: str, route: str, status: int, duration: float) -> None:
    http_metrics.observe(method, route, status, duration)


def log_event(logger, level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, separators=(",", ":")))
