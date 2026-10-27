from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from .config import settings

_worker_client: ContextVar[httpx.Client | None] = ContextVar(
    "judge0_client", default=None
)


@contextmanager
def managed_judge0_client():
    """Own one connection pool for this worker's lifetime."""
    with httpx.Client() as client:
        token = _worker_client.set(client)
        try:
            yield client
        finally:
            _worker_client.reset(token)


@contextmanager
def _request_client():
    client = _worker_client.get()
    if client is not None:
        yield client
    else:
        with httpx.Client() as client:
            yield client


ALLOWED_LIMITS = frozenset(
    {
        "cpu_time_limit",
        "cpu_extra_time",
        "wall_time_limit",
        "memory_limit",
        "stack_limit",
        "max_processes_and_or_threads",
        "max_file_size",
    }
)


def judge0_about(timeout: float = 3.0):
    with _request_client() as c:
        resp = c.get(f"{settings.JUDGE0_URL}/about", timeout=timeout)
        resp.raise_for_status()
        return resp.json()


def judge0_workers(timeout: float = 1.0):
    """Return Judge0's live Resque worker and queue snapshots for operations metrics."""
    with _request_client() as c:
        resp = c.get(f"{settings.JUDGE0_URL}/workers", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError("Judge0 returned an invalid worker status response")
    return data


def judge0_submit(
    source_code: str,
    stdin: str | None = None,
    expected_output: str | None = None,
    wait: bool = True,
    timeout: float = 5.0,
    callback_url: str | None = None,
    **kwargs,
):
    # **kwargs passes per-problem limits through, e.g. cpu_time_limit,
    # wall_time_limit, memory_limit. Needed for TLE/MLE enforcement.
    url = f"{settings.JUDGE0_URL}/submissions?base64_encoded=false"
    if wait:
        url += "&wait=true"
    payload = {"source_code": source_code}
    if stdin is not None:
        payload["stdin"] = stdin
    if expected_output is not None:
        payload["expected_output"] = expected_output
    if callback_url is not None:
        payload["callback_url"] = callback_url

    # drop unknown keys so callers cannot set arbitrary Judge0 fields.
    for key, value in kwargs.items():
        if key in ALLOWED_LIMITS and value is not None:
            payload[key] = value
    with _request_client() as c:
        resp = c.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


def judge0_get(token: str, timeout: float = 3.0):
    with _request_client() as c:
        resp = c.get(
            f"{settings.JUDGE0_URL}/submissions/{token}?base64_encoded=false",
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()


def judge0_group_submit(
    key: str,
    cases: list[dict],
    timeout: float = 5.0,
    *,
    execution_model: str = "fresh",
    shared_script: str | None = None,
):
    payload = {
        "idempotency_key": key,
        "cases": cases,
        "execution_model": execution_model,
    }
    if shared_script is not None:
        payload["shared_script"] = shared_script
    with _request_client() as client:
        response = client.post(
            f"{settings.JUDGE0_URL}/internal/submission-groups",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


def judge0_group_by_key(key: str, timeout: float = 3.0):
    with _request_client() as client:
        response = client.get(
            f"{settings.JUDGE0_URL}/internal/submission-groups/by-key/{key}",
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()
