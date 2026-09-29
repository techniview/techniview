from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from app.models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    AssignmentState,
    CourseMembership,
    MembershipRole,
    Problem,
    StudentAssignmentProgress,
    Submission,
)
from sqlalchemy import select

pytestmark = pytest.mark.anyio

ALL_PASS = [
    {"token": "late-public-token", "status": {"id": 3}},
    {"token": "late-hidden-token", "status": {"id": 3}},
]


async def _login(client, email, password):
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return response


@pytest.fixture
def overdue_context(db_session):
    now = datetime.now(UTC).replace(tzinfo=None)
    instructor = db_session.scalar(
        select(CourseMembership).where(
            CourseMembership.role == MembershipRole.INSTRUCTOR
        )
    )
    student = db_session.scalar(
        select(CourseMembership).where(CourseMembership.role == MembershipRole.STUDENT)
    )
    problem = db_session.scalar(select(Problem).where(Problem.title == "Sum a List"))
    assignment = Assignment(
        course_id=instructor.course_id,
        assigned_by_membership_id=instructor.id,
        title="Overdue work",
        state=AssignmentState.PUBLISHED,
        available_at=now - timedelta(days=10),
        due_at=now - timedelta(days=1),
    )
    db_session.add(assignment)
    db_session.flush()
    item = AssignmentItem(
        assignment_id=assignment.id, problem_id=problem.id, item_order=1
    )
    db_session.add(item)
    db_session.flush()
    db_session.add(
        AssignmentRecipient(
            assignment_id=assignment.id,
            membership_id=student.id,
            course_id=instructor.course_id,
        )
    )
    db_session.commit()
    return {
        "course_id": instructor.course_id,
        "item_id": item.id,
        "problem_id": problem.id,
        "student_user_id": student.user_id,
    }


async def _submit_pass(client, problem_id, item_id):
    with patch("app.routers.submissions.judge0_submit", side_effect=ALL_PASS):
        return await client.post(
            "/api/submissions?wait=true",
            json={
                "source_code": "def sum_list(values):\n    return sum(values)\n",
                "problem_id": problem_id,
                "assignment_item_id": item_id,
            },
        )


async def test_late_submission_excluded_until_approved(client, overdue_context):
    await _login(client, "student@techniview.local", "student-demo")
    response = await _submit_pass(
        client, overdue_context["problem_id"], overdue_context["item_id"]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["is_late"] is True
    assert body["late_approved"] is False
    submission_id = body["id"]

    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = overdue_context["course_id"]
    staff_detail = (
        await client.get(f"/api/courses/{course_id}/submissions/{submission_id}")
    ).json()
    assert staff_detail["is_late"] is True
    assert staff_detail["late_approved"] is False

    approve = await client.post(
        f"/api/courses/{course_id}/submissions/{submission_id}/approve-late"
    )
    assert approve.status_code == 200
    assert approve.json()["late_approved"] is True

    # Idempotent second approval.
    again = await client.post(
        f"/api/courses/{course_id}/submissions/{submission_id}/approve-late"
    )
    assert again.status_code == 200
    assert again.json()["late_approved"] is True


async def test_late_pass_does_not_move_best_until_approved(
    client, db_session, overdue_context
):
    await _login(client, "student@techniview.local", "student-demo")
    await _submit_pass(
        client, overdue_context["problem_id"], overdue_context["item_id"]
    )
    progress = db_session.get(
        StudentAssignmentProgress,
        (overdue_context["student_user_id"], overdue_context["item_id"]),
    )
    assert progress.valid_attempt_count == 1
    assert progress.best_score == 0
    assert progress.first_passed_at is None

    await _login(client, "teacher@techniview.local", "teacher-demo")
    submission = db_session.scalar(
        select(Submission).where(
            Submission.assignment_item_id == overdue_context["item_id"]
        )
    )
    await client.post(
        f"/api/courses/{overdue_context['course_id']}"
        f"/submissions/{submission.id}/approve-late"
    )
    db_session.refresh(progress)
    assert progress.best_score == 1
    assert progress.first_passed_at is not None


async def test_approve_guards(client, overdue_context):
    await _login(client, "student@techniview.local", "student-demo")
    response = await _submit_pass(
        client, overdue_context["problem_id"], overdue_context["item_id"]
    )
    submission_id = response.json()["id"]
    course_id = overdue_context["course_id"]

    forbidden = await client.post(
        f"/api/courses/{course_id}/submissions/{submission_id}/approve-late"
    )
    assert forbidden.status_code == 403

    await _login(client, "teacher@techniview.local", "teacher-demo")
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    await _login(client, "student@techniview.local", "student-demo")
    ta_denied = await client.post(
        f"/api/courses/{course_id}/submissions/{submission_id}/approve-late"
    )
    assert ta_denied.status_code == 403


async def test_approve_on_time_submission_rejected(client, db_session):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    listing = await client.get(f"/api/courses/{course_id}/submissions")
    assert listing.json()["total"] == 0
    # Seeded assignment is due in the future; submit on time via wait flow.
    await _login(client, "student@techniview.local", "student-demo")
    assignments = await client.get(f"/api/courses/{course_id}/assignments")
    on_time_item = assignments.json()["items"][0]["items"][0]
    with patch("app.routers.submissions.judge0_submit", side_effect=ALL_PASS):
        created = await client.post(
            "/api/submissions?wait=true",
            json={
                "source_code": "x",
                "problem_id": on_time_item["problem"]["id"],
                "assignment_item_id": on_time_item["id"],
            },
        )
    assert created.json()["is_late"] is False
    await _login(client, "teacher@techniview.local", "teacher-demo")
    rejected = await client.post(
        f"/api/courses/{course_id}/submissions/{created.json()['id']}/approve-late"
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "not_late"
