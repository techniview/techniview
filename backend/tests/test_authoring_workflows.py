from datetime import datetime, timedelta, timezone

import pytest
from app.core.errors import ApiError
from app.models import (
    Assignment,
    CourseMembership,
    QuestionSetItem,
    User,
    UserRole,
)
from app.routers import assignments, authoring
from sqlalchemy import select
from sqlalchemy.orm import selectinload


def _professor(db):
    return db.scalar(select(User).where(User.email == "teacher@techniview.local"))


def _problem_input():
    return authoring.ProblemInput(
        title="Identity",
        prompt="Return the input.",
        difficulty="easy",
        execution_mode="call_based",
        function_name="identity",
        starter_code="def identity(value): pass",
        canonical_solution="def identity(value): return value",
        tags=[],
        test_cases=[
            authoring.CaseInput(input="[1]", expected_output="1", visibility="public"),
            authoring.CaseInput(input="[2]", expected_output="2", visibility="hidden"),
        ],
    )


def test_canonical_validation_checks_every_case_and_reports_failure(
    db_session, monkeypatch
):
    professor = _professor(db_session)
    created = authoring.create_problem(_problem_input(), db_session, professor)
    calls = []

    def passing_runner(source, **kwargs):
        calls.append((source, kwargs))
        return {"status": {"id": 3}}

    monkeypatch.setattr(authoring, "judge0_submit", passing_runner)
    result = authoring.validate_problem(created["id"], db_session, professor)
    assert result == {"valid": True, "issues": []}
    assert len(calls) == 2

    monkeypatch.setattr(
        authoring,
        "judge0_submit",
        lambda *_args, **_kwargs: {"status": {"id": 4}},
    )
    result = authoring.validate_problem(created["id"], db_session, professor)
    assert result["valid"] is False
    assert result["issues"] == [
        "canonical solution failed test case 1",
        "canonical solution failed test case 2",
    ]


def test_assignment_request_normalizes_aware_timestamps_to_utc():
    timestamp = datetime(2026, 9, 29, 9, 0, tzinfo=timezone(timedelta(hours=-4)))
    request = assignments.AssignmentFromQuestionSet(
        title="Timed",
        question_set_id=1,
        available_at=timestamp,
        due_at=timestamp + timedelta(hours=1),
    )
    assert request.available_at == datetime(2026, 9, 29, 13, 0)
    assert request.available_at.tzinfo is None


def test_problem_and_question_set_are_private_to_their_professor(db_session):
    owner = _professor(db_session)
    other = User(
        name="Another Professor",
        email="another-professor@example.test",
        password_hash="unused",
        role=UserRole.PROFESSOR,
    )
    db_session.add(other)
    db_session.flush()

    created = authoring.create_problem(_problem_input(), db_session, owner)
    with pytest.raises(ApiError) as imported_error:
        authoring.update_problem(1, _problem_input(), db_session, owner)
    assert imported_error.value.status_code == 404
    with pytest.raises(ApiError) as problem_error:
        authoring.update_problem(created["id"], _problem_input(), db_session, other)
    assert problem_error.value.status_code == 404

    question_set = authoring.create_question_set(
        authoring.QuestionSetInput(title="Private set"), db_session, owner
    )
    with pytest.raises(ApiError) as set_error:
        authoring.get_question_set(question_set["id"], db_session, other)
    assert set_error.value.status_code == 404


def test_question_set_cannot_publish_with_an_unpublished_problem(db_session):
    professor = _professor(db_session)
    draft = authoring.create_problem(_problem_input(), db_session, professor)
    question_set = authoring.create_question_set(
        authoring.QuestionSetInput(title="Draft problem set"), db_session, professor
    )
    authoring.replace_items(
        question_set["id"],
        authoring.ItemsInput(problem_ids=[1, draft["id"]]),
        db_session,
        professor,
    )

    with pytest.raises(ApiError) as error:
        authoring.publish_question_set(question_set["id"], db_session, professor)

    assert error.value.code == "unpublished_problems"
    assert (
        authoring._qs(db_session, question_set["id"], professor).state.value == "draft"
    )


def test_replacing_copied_problem_cases_replaces_rows(db_session):
    professor = _professor(db_session)
    copied = authoring.copy_problem(1, db_session, professor)
    replacement = _problem_input()
    replacement.tags = ["arrays"]
    replacement.test_cases = [
        authoring.CaseInput(input="[9]", expected_output="9", visibility="hidden")
    ]

    edited = authoring.update_problem(copied["id"], replacement, db_session, professor)

    assert len(edited["test_cases"]) == 1
    assert edited["test_cases"][0]["input"] == "[9]"
    assert edited["tags"] == ["arrays"]


def test_assignment_items_snapshot_question_set_order(db_session):
    professor = _professor(db_session)
    membership = db_session.scalar(
        select(CourseMembership).where(CourseMembership.user_id == professor.id)
    )
    question_set = authoring.create_question_set(
        authoring.QuestionSetInput(title="Snapshot"), db_session, professor
    )
    set_id = question_set["id"]
    authoring.replace_items(
        set_id, authoring.ItemsInput(problem_ids=[1, 2]), db_session, professor
    )
    authoring.publish_question_set(set_id, db_session, professor)

    result = assignments.create_assignment_from_question_set(
        membership.course_id,
        assignments.AssignmentFromQuestionSet(
            title="Snapshot assignment", question_set_id=set_id
        ),
        db_session,
        professor,
        membership,
    )
    assignment_id = result["id"]
    assert [item["problem"]["id"] for item in result["items"]] == [1, 2]

    source_set = authoring._qs(db_session, set_id, professor)
    source_set.items.clear()
    db_session.flush()
    source_set.items.append(QuestionSetItem(item_order=1, problem_id=2))
    db_session.commit()

    saved = db_session.scalar(
        select(Assignment)
        .options(selectinload(Assignment.items))
        .where(Assignment.id == assignment_id)
    )
    assert [item.problem_id for item in saved.items] == [1, 2]
