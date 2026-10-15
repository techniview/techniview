import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from app.core.errors import ApiError
from app.models import (
    AssignmentItem,
    CourseMembership,
    StudentAssignmentProgress,
    Submission,
    SubmissionStatus,
    User,
)
from app.services.rebuild_progress import rebuild_progress
from app.services.reporting import research_csv
from sqlalchemy import select


def context(db):
    student = db.scalar(select(User).where(User.email == "student@techniview.local"))
    membership = db.scalar(
        select(CourseMembership).where(CourseMembership.user_id == student.id)
    )
    item = db.scalar(select(AssignmentItem))
    return student, membership, item


@pytest.mark.anyio
async def test_exports_require_staff_and_keep_withdrawn_grades(
    teacher_client, student_client, db_session
):
    student, membership, item = context(db_session)
    path = f"/api/courses/{membership.course_id}/exports/grades.csv"
    assert (await student_client.get(path)).status_code == 403
    membership.withdrawn_at = datetime.now()
    student.email = "=formula@example.com"
    db_session.commit()
    response = await teacher_client.get(path)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows
    assert rows[0]["email"] == "'=formula@example.com"
    assert rows[0]["withdrawn"] == "True"
    assert any(int(row["assignment_item_id"]) == item.id for row in rows)


@pytest.mark.anyio
async def test_research_export_has_stable_pseudonyms_and_no_payload(
    teacher_client, db_session, monkeypatch
):
    student, membership, item = context(db_session)
    db_session.add(
        Submission(
            student_id=student.id,
            problem_id=item.problem_id,
            assignment_item_id=item.id,
            source_code="PRIVATE SOURCE",
            status=SubmissionStatus.PASSED,
            score=1,
            python_exception_type="PRIVATE FREE TEXT",
        )
    )
    db_session.commit()
    path = f"/api/courses/{membership.course_id}/exports/research.csv"
    assert (await teacher_client.get(path)).status_code == 404
    monkeypatch.delenv("RESEARCH_EXPORT_SECRET", raising=False)
    with pytest.raises(ApiError) as unconfigured:
        research_csv(db_session, membership.course_id, item.assignment_id, "study-one")
    assert unconfigured.value.status_code == 503
    monkeypatch.setenv("RESEARCH_EXPORT_SECRET", "test-only-secret" * 3)
    first = research_csv(
        db_session, membership.course_id, item.assignment_id, "study-one"
    )
    second = research_csv(
        db_session, membership.course_id, item.assignment_id, "study-one"
    )
    assert first == second
    assert "PRIVATE" not in first
    assert student.email not in first
    row = next(csv.DictReader(io.StringIO(first)))
    assert len(row["participant"]) == 64
    assert "student_id" not in row
    assert "problem_id" not in row
    assert "assignment_item_id" not in row
    assert len(row["context"]) == 64


def test_rebuild_is_repeatable_and_preserves_open_and_late_rules(db_session):
    student, _, item = context(db_session)
    start = datetime(2026, 1, 1)
    progress = db_session.get(StudentAssignmentProgress, (student.id, item.id))
    progress.first_opened_at = start
    progress.best_score = Decimal("0.99")
    for index, (status, score, late, approved) in enumerate(
        [
            (SubmissionStatus.PASSED, 1, True, False),
            (SubmissionStatus.FAILED, Decimal("0.4"), False, False),
            (SubmissionStatus.INFRASTRUCTURE_ERROR, 1, False, False),
            (SubmissionStatus.PASSED, 1, True, True),
        ]
    ):
        when = start + timedelta(hours=index + 1)
        db_session.add(
            Submission(
                student_id=student.id,
                problem_id=item.problem_id,
                assignment_item_id=item.id,
                source_code="x",
                status=status,
                score=score,
                is_late=late,
                late_approved_at=when if approved else None,
                submitted_at=when,
                completed_at=when,
            )
        )
    db_session.flush()
    for _ in range(2):
        assert rebuild_progress(db_session) == 4
        assert progress.first_opened_at == start
        assert progress.first_passed_at == start + timedelta(hours=4)
        assert progress.valid_attempt_count == 3
        assert progress.retry_count == 2
        assert progress.best_score == 1


@pytest.mark.anyio
async def test_student_analytics_filters_and_pagination(student_client, db_session):
    _, membership, _ = context(db_session)
    response = await student_client.get(
        "/api/me/analytics",
        params={
            "scope": "assignments",
            "course_id": membership.course_id,
            "limit": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] == 2
    assert body["metrics"]["assigned_count"] == 2
    assert (
        await student_client.get("/api/me/analytics", params={"course_id": 99999})
    ).status_code == 404


def test_summaries_include_historical_recipients_and_fractional_time(db_session):
    from app.models import CourseProblemAnalytics, MembershipRole
    from app.services.summaries import refresh_course_problem

    student, membership, item = context(db_session)
    progress = db_session.get(StudentAssignmentProgress, (student.id, item.id))
    membership.withdrawn_at = datetime.now()
    membership.role = MembershipRole.TA
    progress.first_opened_at = datetime(2026, 1, 1)
    progress.first_passed_at = progress.first_opened_at + timedelta(seconds=0.125)
    refresh_course_problem(db_session, membership.course_id, item.problem_id)
    summary = db_session.get(
        CourseProblemAnalytics, (membership.course_id, item.problem_id)
    )
    assert summary.assigned_count == 1
    assert summary.completed_count == 1
    assert summary.completion_seconds_sum == Decimal("0.125")
    assert summary.valid_attempt_count == progress.valid_attempt_count


@pytest.mark.anyio
async def test_research_export_is_not_an_instructor_route(
    teacher_client, db_session, monkeypatch
):
    _student, membership, _item = context(db_session)
    monkeypatch.setenv("RESEARCH_EXPORT_SECRET", "test-only-secret" * 3)
    path = f"/api/courses/{membership.course_id}/exports/research.csv"
    assert (await teacher_client.get(path)).status_code == 404
    with pytest.raises(ApiError) as missing:
        research_csv(db_session, membership.course_id, 99999, "study")
    assert missing.value.status_code == 404


def test_research_publications_use_distinct_pseudonyms(db_session, monkeypatch):
    from app.services.reporting import research_csv

    student, membership, item = context(db_session)
    monkeypatch.setenv("RESEARCH_EXPORT_SECRET", "test-only-secret" * 3)
    db_session.add(
        Submission(
            student_id=student.id,
            problem_id=item.problem_id,
            assignment_item_id=item.id,
            source_code="secret",
            status=SubmissionStatus.PASSED,
        )
    )
    db_session.flush()
    first = next(
        csv.DictReader(
            io.StringIO(
                research_csv(
                    db_session, membership.course_id, item.assignment_id, "one"
                )
            )
        )
    )
    second = next(
        csv.DictReader(
            io.StringIO(
                research_csv(
                    db_session, membership.course_id, item.assignment_id, "two"
                )
            )
        )
    )
    for field in ("participant", "problem", "context"):
        assert first[field] != second[field]
    assert first["seconds_since_first_attempt"] == "0.0"


def test_summary_exception_counts_exclude_infrastructure(db_session):
    from app.models import CourseProblemErrorCount
    from app.services.summaries import refresh_course_problem

    student, membership, item = context(db_session)
    for status in (
        SubmissionStatus.RUNTIME_ERROR,
        SubmissionStatus.INFRASTRUCTURE_ERROR,
    ):
        db_session.add(
            Submission(
                student_id=student.id,
                problem_id=item.problem_id,
                assignment_item_id=item.id,
                source_code="x",
                status=status,
                completed_at=datetime.now(),
                python_exception_type="ValueError",
            )
        )
    refresh_course_problem(db_session, membership.course_id, item.problem_id)
    error = db_session.get(
        CourseProblemErrorCount, (membership.course_id, item.problem_id, "ValueError")
    )
    assert error.error_count == 1


def test_summary_refresh_uses_current_reads(db_session):
    from app.services.summaries import refresh_course_problem
    from sqlalchemy import event
    from sqlalchemy.dialects import mysql

    _, membership, item = context(db_session)
    statements = []

    def capture(state):
        if state.is_select:
            statements.append(str(state.statement.compile(dialect=mysql.dialect())))

    event.listen(db_session, "do_orm_execute", capture)
    try:
        refresh_course_problem(db_session, membership.course_id, item.problem_id)
    finally:
        event.remove(db_session, "do_orm_execute", capture)
    for table in (
        "course_problem_analytics",
        "student_assignment_progress",
        "submissions",
    ):
        reads = [
            sql
            for sql in statements
            if f"FROM {table}" in sql or f"JOIN {table}" in sql
        ]
        assert reads
        assert all("FOR UPDATE" in sql for sql in reads)
