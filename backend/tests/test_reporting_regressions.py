from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from alembic import command
from alembic.config import Config
from app.core.config import build_database_url, settings
from app.models import (
    Assignment,
    AssignmentItem,
    AssignmentState,
    CourseMembership,
    Problem,
    StudentAssignmentProgress,
    Submission,
    SubmissionCaseResult,
    SubmissionStatus,
    User,
    UserSession,
)
from app.routers.submissions import (
    SubmissionCreate,
    create_submission,
    receive_judge0_callback,
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
    )
    assert response["status"] == SubmissionStatus.QUEUED
    return response["id"]


def test_callback_decodes_report_and_duplicate_delivery_is_immutable(db_session):
    sid = _create(db_session)
    with patch(
        "app.worker.submissions.judge0_submit", return_value={"token": "text-token"}
    ) as submit:
        assert process_next_submission(db_session, "decode-worker")
    secret = submit.call_args.kwargs["callback_url"].rsplit("/", 1)[1]
    report = {
        "token": "text-token",
        "status": {"id": 3},
        "stdout": "Mg\no=\n",
        "stderr": "w6kK",
    }
    assert receive_judge0_callback(secret, report, db_session) == {"ok": True}
    assert receive_judge0_callback(
        secret, {**report, "stdout": "YmFk"}, db_session
    ) == {"ok": True}
    case = db_session.get(Submission, sid).case_results[0]
    assert case.stdout == "2\n" and case.stderr == "é\n"


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
    assert config.get_main_option("sqlalchemy.url") == url
    for model, name in (
        (UserSession, "token_hash"),
        (SubmissionCaseResult, "callback_token_hash"),
    ):
        assert model.__table__.c[name].type.compile(mysql.dialect()) == "BINARY(32)"


def test_dispatch_failure_does_not_consume_attempt_and_never_resends(db_session):
    sid = _create(db_session)
    with patch(
        "app.worker.submissions.judge0_submit", side_effect=httpx.ConnectError("down")
    ) as submit:
        assert process_next_submission(db_session, "failure-worker")
    row = db_session.get(Submission, sid)
    assert row.status == SubmissionStatus.QUEUED
    assert all(case.dispatch_started_at for case in row.case_results)
    row.next_check_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    with patch("app.worker.submissions.judge0_submit") as retry:
        assert process_next_submission(db_session, "retry-worker")
    retry.assert_not_called()
    assert submit.call_count == 1
    for case in row.case_results:
        case.dispatch_started_at = utc_now() - timedelta(minutes=11)
    row.next_check_at = utc_now() - timedelta(seconds=1)
    db_session.commit()
    assert process_next_submission(db_session, "expiry-worker")
    assert row.status == SubmissionStatus.INFRASTRUCTURE_ERROR
    user, problem = _context(db_session)
    from app.models import StudentPracticeProgress

    progress = db_session.get(StudentPracticeProgress, (user.id, problem.id))
    assert progress.valid_attempt_count == 0


@pytest.mark.parametrize("delivery", ["poll", "callback"])
@pytest.mark.parametrize("access_change", ["archive", "withdraw"])
def test_reserved_assignment_finishes_after_access_changes(
    db_session, delivery, access_change
):
    user, problem = _context(db_session)
    item = db_session.scalar(
        select(AssignmentItem).where(AssignmentItem.problem_id == problem.id)
    )
    sid = _create(db_session, item.id)
    with patch(
        "app.worker.submissions.judge0_submit", return_value={"token": "late-token"}
    ) as submit:
        assert process_next_submission(db_session, "dispatch-worker")
    if access_change == "archive":
        db_session.get(Assignment, item.assignment_id).state = AssignmentState.ARCHIVED
    else:
        membership = db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == user.id)
        )
        membership.withdrawn_at = datetime.now()
    db_session.commit()
    report = {"token": "late-token", "status": {"id": 3}}
    if delivery == "callback":
        secret = submit.call_args.kwargs["callback_url"].rsplit("/", 1)[1]
        receive_judge0_callback(secret, report, db_session)
        receive_judge0_callback(secret, report, db_session)
    else:
        row = db_session.get(Submission, sid)
        row.next_check_at = utc_now() - timedelta(seconds=1)
        db_session.commit()
        with patch("app.worker.submissions.judge0_get", return_value=report):
            assert process_next_submission(db_session, "poll-worker")
    db_session.expire_all()
    assert db_session.get(Submission, sid).status == SubmissionStatus.PASSED
    progress = db_session.get(StudentAssignmentProgress, (user.id, item.id))
    assert progress.valid_attempt_count == 1 and progress.best_score == 1
