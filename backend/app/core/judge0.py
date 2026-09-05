import httpx

from .config import settings


def judge0_about(timeout: float = 3.0):
    with httpx.Client(timeout=timeout) as c:
        resp = c.get(f"{settings.JUDGE0_URL}/about")
        resp.raise_for_status()
        return resp.json()


def judge0_submit(
    source_code: str,
    language_id: int = 71,
    stdin: str | None = None,
    expected_output: str | None = None,
    wait: bool = True,
    timeout: float = 5.0,
    **kwargs,
):
    # **kwargs passes per-problem limits through, e.g. cpu_time_limit,
    # wall_time_limit, memory_limit. Needed for TLE/MLE enforcement.
    url = f"{settings.JUDGE0_URL}/submissions?base64_encoded=false"
    if wait:
        url += "&wait=true"
    payload = {"source_code": source_code, "language_id": language_id}
    if stdin is not None:
        payload["stdin"] = stdin
    if expected_output is not None:
        payload["expected_output"] = expected_output
    payload.update(kwargs)
    with httpx.Client(timeout=timeout) as c:
        resp = c.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


def judge0_get(token: str, timeout: float = 3.0):
    with httpx.Client(timeout=timeout) as c:
        resp = c.get(f"{settings.JUDGE0_URL}/submissions/{token}?base64_encoded=false")
        resp.raise_for_status()
        return resp.json()
