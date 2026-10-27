import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.judge0 import _worker_client
from app.models import SubmissionStatus
from app.worker import submissions


def test_dispatch_pool_owns_sessions_and_keeps_claim_until_all_cases_finish(
    monkeypatch,
):
    original = submissions.process_submission
    outer_db = MagicMock()
    row = SimpleNamespace(
        claim_owner="owner",
        claimed_at=None,
        next_check_at=None,
        status=SubmissionStatus.RUNNING,
        case_results=[SimpleNamespace(test_case_id=i) for i in range(4)],
    )
    barrier = threading.Barrier(4, timeout=5)
    sessions = []
    processed = []
    client = object()

    def session_factory():
        db = MagicMock()
        db.__enter__.return_value = db
        sessions.append(db)
        return db

    def intercept(db, submission_id, owner, **kwargs):
        if kwargs.get("case_ids_override") is None:
            return original(db, submission_id, owner, **kwargs)
        assert db is not outer_db
        assert row.claim_owner == owner
        assert kwargs["release_claim"] is False
        assert _worker_client.get() is client
        barrier.wait()
        processed.extend(kwargs["case_ids_override"])

    monkeypatch.setattr(submissions.settings, "WORKER_DISPATCH_CONCURRENCY", 4)
    monkeypatch.setattr(submissions, "SessionLocal", session_factory)
    monkeypatch.setattr(submissions, "process_submission", intercept)
    monkeypatch.setattr(submissions.results, "_load_submission", lambda *args: row)
    monkeypatch.setattr(submissions.results, "_finalize_submission", lambda *args: None)
    monkeypatch.setattr(submissions, "_schedule_submission", lambda *args: None)
    token = _worker_client.set(client)
    try:
        intercept(outer_db, 42, "owner")
    finally:
        _worker_client.reset(token)
    assert sorted(processed) == [0, 1, 2, 3]
    assert len({id(db) for db in sessions}) == 4
    assert all(db.__exit__.called for db in sessions)
    assert row.claim_owner is None
