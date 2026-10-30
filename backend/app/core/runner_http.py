"""Reuse one HTTP connection pool per application worker."""

from contextlib import contextmanager
from contextvars import ContextVar

import httpx

_worker_client: ContextVar[httpx.Client | None] = ContextVar(
    "runner_client", default=None
)


@contextmanager
def managed_runner_client():
    with httpx.Client() as client:
        token = _worker_client.set(client)
        try:
            yield client
        finally:
            _worker_client.reset(token)


@contextmanager
def request_client():
    client = _worker_client.get()
    if client is not None:
        yield client
    else:
        with httpx.Client() as client:
            yield client
