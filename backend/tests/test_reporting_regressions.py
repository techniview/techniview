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
    SubmissionStatus,
    User,
)
from app.routers.submissions import (
    SubmissionCreate,
    create_submission,
    get_submission,
    receive_judge0_callback,
)
from sqlalchemy import select
from sqlalchemy.dialects import mysql


@pytest.mark.parametrize("source", ["a" * 65535, "é" * 32767 + "a"])
def test_source_accepts_utf8_byte_boundary(source):
    assert SubmissionCreate(source_code=source, problem_id=1).source_code == source


@pytest.mark.parametrize("source", ["a" * 65536, "é" * 32768])
def test_source_rejects_utf8_byte_overflow(source):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SubmissionCreate(source_code=source, problem_id=1)


def test_callback_decodes_report_after_polling(db_session):
    user, problem = _context(db_session)
    with patch(
        "app.routers.submissions.judge0_submit", return_value={"token": "text-token"}
    ) as submit:
        response = create_submission(
            SubmissionCreate(source_code="print(2)", problem_id=problem.id),
            db_session,
            user,
        )
    report = {"token": "text-token", "status": {"id": 3}, "stdout": "2\n"}
    with patch("app.routers.submissions.judge0_get", return_value=report):
        get_submission(response["id"], db_session, user)
    secret = submit.call_args.kwargs["callback_url"].rsplit("/", 1)[1]
    receive_judge0_callback(
        secret,
        {
            **report,
            "stdout": "Mg\no=\n",
            "stderr": "w6kK",
            "compile_output": None,
        },
        db_session,
    )
    result = db_session.get(Submission, response["id"]).case_results[0]
    assert result.stdout == "2\n"
    assert result.stderr == "é\n"
    assert result.compile_output is None


def test_finalization_reads_cases_with_mysql_row_locks(db_session):
    from app.routers.submissions import _load_submission
    from sqlalchemy import event

    user, problem = _context(db_session)
    with patch(
        "app.routers.submissions.judge0_submit", return_value={"token": "lock-token"}
    ):
        response = create_submission(
            SubmissionCreate(source_code="print(2)", problem_id=problem.id),
            db_session,
            user,
        )
    statements = []

    def capture(state):
        statements.append(str(state.statement.compile(dialect=mysql.dialect())))

    event.listen(db_session, "do_orm_execute", capture)
    try:
        _load_submission(db_session, response["id"])
    finally:
        event.remove(db_session, "do_orm_execute", capture)
    case_reads = [sql for sql in statements if "FROM submission_case_results" in sql]
    assert case_reads
    assert all("FOR UPDATE" in sql for sql in case_reads)


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
    from app.models import SubmissionCaseResult, UserSession

    for model, name in (
        (UserSession, "token_hash"),
        (SubmissionCaseResult, "callback_token_hash"),
    ):
        assert model.__table__.c[name].type.compile(mysql.dialect()) == "BINARY(32)"


def _context(db):
    user = db.scalar(select(User).where(User.email == "student@techniview.local"))
    problem = db.scalar(select(Problem).where(Problem.title == "Count Evens"))
    return user, problem


def test_wait_submission_refreshes_preloaded_empty_cases(db_session):
    user, problem = _context(db_session)
    with patch(
        "app.routers.submissions.judge0_submit",
        return_value={"token": "wait-token", "status": {"id": 3}},
    ):
        response = create_submission(
            SubmissionCreate(source_code="print(2)", problem_id=problem.id),
            db_session,
            user,
            wait=True,
        )
    assert response["test_count"] == 1
    assert response["done"] is True
    assert response["status"] == SubmissionStatus.PASSED


def test_dispatch_failure_finalizes_reserved_submission(db_session):
    from fastapi import HTTPException

    user, problem = _context(db_session)
    with (
        patch(
            "app.routers.submissions.judge0_submit",
            side_effect=httpx.ConnectError("runner unavailable"),
        ),
        pytest.raises(HTTPException),
    ):
        create_submission(
            SubmissionCreate(source_code="print(2)", problem_id=problem.id),
            db_session,
            user,
        )
    submission = db_session.scalar(select(Submission))
    assert submission.status == SubmissionStatus.INFRASTRUCTURE_ERROR
    assert submission.completed_at is not None
    assert len(submission.case_results) == 1


@pytest.mark.parametrize("delivery", ["poll", "callback"])
@pytest.mark.parametrize("access_change", ["archive", "withdraw"])
def test_reserved_assignment_finalizes_after_access_changes(
    db_session, delivery, access_change
):
    from datetime import datetime

    user, problem = _context(db_session)
    item = db_session.scalar(
        select(AssignmentItem).where(AssignmentItem.problem_id == problem.id)
    )
    with patch(
        "app.routers.submissions.judge0_submit", return_value={"token": "late-token"}
    ) as submit:
        response = create_submission(
            SubmissionCreate(
                source_code="print(2)",
                problem_id=problem.id,
                assignment_item_id=item.id,
            ),
            db_session,
            user,
        )
    if access_change == "archive":
        db_session.get(Assignment, item.assignment_id).state = AssignmentState.ARCHIVED
    else:
        membership = db_session.scalar(
            select(CourseMembership).where(CourseMembership.user_id == user.id)
        )
        membership.withdrawn_at = datetime.now()
    db_session.commit()
    report = {"token": "late-token", "status": {"id": 3}}
    if delivery == "poll":
        with patch("app.routers.submissions.judge0_get", return_value=report):
            get_submission(response["id"], db_session, user)
            get_submission(response["id"], db_session, user)
    else:
        secret = submit.call_args.kwargs["callback_url"].rsplit("/", 1)[1]
        receive_judge0_callback(secret, report, db_session)
        receive_judge0_callback(secret, report, db_session)
    submission = db_session.get(Submission, response["id"])
    progress = db_session.get(StudentAssignmentProgress, (user.id, item.id))
    assert submission.status == SubmissionStatus.PASSED
    assert progress.valid_attempt_count == 1
    assert progress.best_score == 1
