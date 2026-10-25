"""Small Prometheus text registry for app-level operational signals."""

import json
import logging
import sys
import threading
import time
from collections import defaultdict


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
    methods = frozenset(
        {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
    )

    def __init__(self):
        self._lock = threading.Lock()
        self._requests = defaultdict(int)
        self._duration_sums = defaultdict(float)
        self._duration_counts = defaultdict(int)
        self._duration_buckets = defaultdict(lambda: [0] * len(self.duration_buckets))

    def observe(self, method: str, route: str, status: int, duration: float) -> None:
        method = method if method in self.methods else "OTHER"
        key = (method, route, status)
        with self._lock:
            self._requests[key] += 1
            self._duration_sums[key] += duration
            self._duration_counts[key] += 1
            for index, bound in enumerate(self.duration_buckets):
                if duration <= bound:
                    self._duration_buckets[key][index] += 1

    def render(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            duration_sums = dict(self._duration_sums)
            duration_counts = dict(self._duration_counts)
            duration_buckets = {
                key: values[:] for key, values in self._duration_buckets.items()
            }
        lines = [
            "# HELP techniview_http_requests_total Completed HTTP requests.",
            "# TYPE techniview_http_requests_total counter",
        ]
        for (method, route, status), count in sorted(requests.items()):
            labels = _labels(method=method, route=route, status=str(status))
            lines.append(f"techniview_http_requests_total{labels} {count}")
        lines.extend(
            [
                "# HELP techniview_http_request_duration_seconds HTTP duration.",
                "# TYPE techniview_http_request_duration_seconds histogram",
            ]
        )
        for key, count in sorted(duration_counts.items()):
            method, route, status = key
            for index, bound in enumerate(self.duration_buckets):
                labels = _labels(
                    method=method,
                    route=route,
                    status=str(status),
                    le=f"{bound:g}",
                )
                lines.append(
                    f"techniview_http_request_duration_seconds_bucket{labels} "
                    f"{duration_buckets[key][index]}"
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
                f"{duration_sums[key]:.6f}"
            )
        return "\n".join(lines) + "\n"


def _labels(**values: str) -> str:
    escaped = []
    for name, value in values.items():
        value = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        escaped.append(f'{name}="{value}"')
    return "{" + ",".join(escaped) + "}"


http_metrics = HttpMetrics()


def observe_request(method: str, route: str, status: int, started_at: float) -> None:
    http_metrics.observe(method, route, status, time.perf_counter() - started_at)


def log_event(logger, level: int, event: str, **fields) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, separators=(",", ":")))
