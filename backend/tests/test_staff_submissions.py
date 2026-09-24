from decimal import Decimal

import pytest
from app.models import (
    Assignment,
    AssignmentItem,
    AssignmentState,
    Course,
    CourseMembership,
    MembershipRole,
    Problem,
    ProblemTestCase,
    Submission,
    SubmissionCaseResult,
    SubmissionStatus,
    User,
)
from sqlalchemy import select

pytestmark = pytest.mark.anyio


async def _login(client, email, password):
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return response


def _seed_submission(db_session, *, student_id, problem_id, item_id, status, source):
    submission = Submission(
        student_id=student_id,
        problem_id=problem_id,
        assignment_item_id=item_id,
        source_code=source,
        status=status,
        score=Decimal("0.5") if status != SubmissionStatus.QUEUED else None,
    )
    db_session.add(submission)
    db_session.flush()
    cases = db_session.scalars(
        select(ProblemTestCase)
        .where(ProblemTestCase.problem_id == problem_id)
        .order_by(ProblemTestCase.case_order)
    ).all()
    for case in cases:
        db_session.add(
            SubmissionCaseResult(
                submission_id=submission.id,
                test_case_id=case.id,
                judge0_token=f"token-{submission.id}-{case.id}"[:36],
                judge0_status_id=4,
                stdout="some output",
                stderr="",
            )
        )
    db_session.commit()
    return submission


@pytest.fixture
def course_context(db_session):
    course = db_session.scalar(select(Course).where(Course.name == "CS 101 Demo"))
    student = db_session.scalar(
        select(User).where(User.email == "student@techniview.local")
    )
    problem = db_session.scalar(select(Problem).where(Problem.title == "Sum a List"))
    item = db_session.scalar(
        select(AssignmentItem).where(AssignmentItem.problem_id == problem.id)
    )
    submission = _seed_submission(
        db_session,
        student_id=student.id,
        problem_id=problem.id,
        item_id=item.id,
        status=SubmissionStatus.FAILED,
        source="def sum_list(values):\n    return 0\n",
    )
    return {
        "course_id": course.id,
        "student_id": student.id,
        "problem_id": problem.id,
        "item_id": item.id,
        "assignment_id": item.assignment_id,
        "submission_id": submission.id,
    }


async def test_instructor_lists_and_inspects_with_redaction(client, course_context):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = course_context["course_id"]

    listing = await client.get(f"/api/courses/{course_id}/submissions")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["source_code"].startswith("def sum_list")
    assert body["items"][0]["student_id"] == course_context["student_id"]

    detail = await client.get(
        f"/api/courses/{course_id}/submissions/{course_context['submission_id']}"
    )
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["source_code"].startswith("def sum_list")
    assert len(payload["cases"]) == 2
    public = next(case for case in payload["cases"] if case["visibility"] == "public")
    hidden = next(case for case in payload["cases"] if case["visibility"] == "hidden")
    assert public["input"] == "[[1, 2, 3]]"
    assert public["expected_output"] == "6"
    assert "input" not in hidden
    assert "expected_output" not in hidden
    assert hidden["stdout"] == "some output"


async def test_ta_allowed_student_denied(client, course_context):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = course_context["course_id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    await _login(client, "student@techniview.local", "student-demo")
    assert (
        await client.get(f"/api/courses/{course_id}/submissions")
    ).status_code == 200

    await _login(client, "teacher@techniview.local", "teacher-demo")
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "student"},
    )
    await _login(client, "student@techniview.local", "student-demo")
    assert (
        await client.get(f"/api/courses/{course_id}/submissions")
    ).status_code == 403


async def test_list_filters_and_scoping(client, db_session, course_context):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = course_context["course_id"]

    filtered = await client.get(
        f"/api/courses/{course_id}/submissions",
        params={"student_id": course_context["student_id"], "status": "failed"},
    )
    assert filtered.json()["total"] == 1

    empty = await client.get(
        f"/api/courses/{course_id}/submissions", params={"status": "passed"}
    )
    assert empty.json()["total"] == 0

    unknown_student = await client.get(
        f"/api/courses/{course_id}/submissions", params={"student_id": 999999}
    )
    assert unknown_student.status_code == 404

    # Practice submissions (no assignment item) are not class work.
    practice = Submission(
        student_id=course_context["student_id"],
        problem_id=course_context["problem_id"],
        assignment_item_id=None,
        source_code="practice",
        status=SubmissionStatus.FAILED,
    )
    db_session.add(practice)
    db_session.commit()
    assert (
        await client.get(f"/api/courses/{course_id}/submissions/{practice.id}")
    ).status_code == 404
    assert (await client.get(f"/api/courses/{course_id}/submissions")).json()[
        "total"
    ] == 1


async def test_other_course_submission_not_visible(client, db_session, course_context):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    other_course = Course(name="Other", join_code_hash=None)
    db_session.add(other_course)
    db_session.flush()
    instructor = db_session.scalar(
        select(CourseMembership).where(
            CourseMembership.role == MembershipRole.INSTRUCTOR
        )
    )
    other_membership = CourseMembership(
        course_id=other_course.id,
        user_id=instructor.user_id,
        role=MembershipRole.INSTRUCTOR,
    )
    db_session.add(other_membership)
    db_session.flush()
    assignment = Assignment(
        course_id=other_course.id,
        assigned_by_membership_id=other_membership.id,
        title="Other assignment",
        state=AssignmentState.PUBLISHED,
    )
    db_session.add(assignment)
    db_session.flush()
    item = AssignmentItem(
        assignment_id=assignment.id,
        problem_id=course_context["problem_id"],
        item_order=1,
    )
    db_session.add(item)
    db_session.flush()
    other_submission = _seed_submission(
        db_session,
        student_id=course_context["student_id"],
        problem_id=course_context["problem_id"],
        item_id=item.id,
        status=SubmissionStatus.FAILED,
        source="other",
    )
    first_course_id = course_context["course_id"]
    assert (
        await client.get(
            f"/api/courses/{first_course_id}/submissions/{other_submission.id}"
        )
    ).status_code == 404
    assert (await client.get(f"/api/courses/{first_course_id}/submissions")).json()[
        "total"
    ] == 1
