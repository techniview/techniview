from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import build_database_url, settings
from app.core.errors import ApiError
from app.models import (
    Assignment,
    AssignmentItem,
    AssignmentState,
    CourseMembership,
    Problem,
    Submission,
    SubmissionCaseResult,
    SubmissionStatus,
    User,
    UserSession,
)
from app.routers.submissions import (
    SubmissionCreate,
    create_submission,
)
from app.services.progress import utc_now
from app.worker.submissions import process_next_submission
from sqlalchemy import event, select
from sqlalchemy.dialects import mysql


@pytest.mark.parametrize("source", ["a" * 65535, "é" * 32767 + "a"])
def test_source_accepts_utf8_byte_boundary(source):
    assert SubmissionCreate(source_code=source, problem_id=1).source_code == source


@pytest.mark.parametrize("source", ["a" * 65536, "é" * 32768])
def test_source_rejects_utf8_byte_overflow(source):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SubmissionCreate(source_code=source, problem_id=1)


def _context(db):
    user = db.scalar(select(User).where(User.email == "student@techniview.local"))
    problem = db.scalar(select(Problem).where(Problem.title == "Count Evens"))
    return user, problem


def _create(db, assignment_item_id=None):
    user, problem = _context(db)
    response = create_submission(
        SubmissionCreate(
            source_code="print(2)",
            problem_id=problem.id,
            assignment_item_id=assignment_item_id,
        ),
        db,
        user,
        idempotency_key=uuid4().hex,
    )
    assert response["status"] == SubmissionStatus.QUEUED
    return response["id"]


def test_finalization_reads_cases_with_mysql_row_locks(db_session):
    from app.routers.submissions import _load_submission

    sid = _create(db_session)
    statements = []

    def capture(state):
        statements.append(str(state.statement.compile(dialect=mysql.dialect())))

    event.listen(db_session, "do_orm_execute", capture)
    try:
        _load_submission(db_session, sid)
    finally:
        event.remove(db_session, "do_orm_execute", capture)
    reads = [s for s in statements if "FROM submission_case_results" in s]
    assert reads and all("FOR UPDATE" in s for s in reads)


def test_graded_idempotency_reuses_submission_and_rejects_changed_payload(db_session):
    user, problem = _context(db_session)
    key = uuid4().hex
    body = SubmissionCreate(problem_id=problem.id, source_code="print(2)")
    first = create_submission(body, db_session, user, idempotency_key=key)
    retry = create_submission(body, db_session, user, idempotency_key=key)
    assert first["id"] == retry["id"]

    changed = SubmissionCreate(problem_id=problem.id, source_code="print(3)")
    with pytest.raises(ApiError) as error:
        create_submission(changed, db_session, user, idempotency_key=key)
    assert error.value.code == "idempotency_key_reused"


def test_public_run_idempotency_expires_and_allows_intentional_repeat(db_session):
    from app.models import SubmissionIdempotencyKey
    from app.routers.problems import RunRequest, run_public_cases

    user, problem = _context(db_session)
    key = uuid4().hex
    body = RunRequest(source_code="print(2)")
    first = run_public_cases(problem.id, body, db_session, user, idempotency_key=key)
    retry = run_public_cases(problem.id, body, db_session, user, idempotency_key=key)
    assert first["id"] == retry["id"]

    record = db_session.scalar(
        select(SubmissionIdempotencyKey).where(
            SubmissionIdempotencyKey.operation == "public_run"
        )
    )
    record.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    expired_retry = run_public_cases(
        problem.id, body, db_session, user, idempotency_key=key
    )
    assert expired_retry["id"] != first["id"]

    intentional = run_public_cases(
        problem.id, body, db_session, user, idempotency_key=uuid4().hex
    )
    assert intentional["id"] != expired_retry["id"]


def test_mysql_migrations_support_indexed_hashes_and_encoded_credentials(monkeypatch):
    backend = Path(__file__).resolve().parents[1]
    output = StringIO()
    config = Config(str(backend / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(backend / "migrations"))
    url = build_database_url("user", "p@ss%word", "localhost", 3306, "test")
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "token_hash BINARY(32)" in sql
    assert "callback_token_hash BINARY(32)" in sql
    assert "CREATE TABLE submission_idempotency_keys" in sql
    assert "request_fingerprint BINARY(32)" in sql
    assert "failure_code VARCHAR(32)" in sql
    assert config.get_main_option("sqlalchemy.url") == url
    for model, name in (
        (UserSession, "token_hash"),
        (SubmissionCaseResult, "callback_token_hash"),
    ):
        assert model.__table__.c[name].type.compile(mysql.dialect()) == "BINARY(32)"


def test_unknown_go_judge_outcome_never_resends(db_session):
    from app.core import go_judge

    sid = _create(db_session)
    with patch("app.core.go_judge.execute", side_effect=go_judge.OutcomeUnknown):
        assert process_next_submission(db_session, "failure-worker")
    row = db_session.get(Submission, sid)
    assert row.status == SubmissionStatus.INFRASTRUCTURE_ERROR
    assert row.failure_code == "runner_outcome_unknown"
    assert all(case.dispatch_attempt_count == 1 for case in row.case_results)
    with patch("app.core.go_judge.execute") as retry:
        assert not process_next_submission(db_session, "retry-worker")
    retry.assert_not_called()


@pytest.mark.parametrize("access_change", ["archive", "withdraw"])
def test_reserved_assignment_finishes_after_access_changes(db_session, access_change):
    user, problem = _context(db_session)
    item = db_session.scalar(
        select(AssignmentItem).where(AssignmentItem.problem_id == problem.id)
    )
    sid = _create(db_session, item.id)
    if access_change == "archive":
        db_session.get(Assignment, item.assignment_id).state = AssignmentState.ARCHIVED
    else:
        membership = db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == user.id)
        )
        membership.withdrawn_at = datetime.now()
    db_session.commit()

    def passed(execution):
        return {
            "status": {"id": 3},
            "stdout": execution.expected + "\n",
            "time": 0.01,
            "memory": 128,
        }

    with patch("app.core.go_judge.execute", side_effect=passed):
        assert process_next_submission(db_session, "execution-worker")
    row = db_session.get(Submission, sid)
    assert row.status == SubmissionStatus.PASSED
    assert all(case.dispatch_attempt_count == 1 for case in row.case_results)
