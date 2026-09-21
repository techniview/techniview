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
    StudentPracticeProgress,
)
from sqlalchemy import func, select

pytestmark = pytest.mark.anyio


async def test_auth_session_lifecycle(client):
    unauthorized = await client.get("/api/auth/me")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "authentication_required"

    invalid = await client.post(
        "/api/auth/login",
        json={"email": "teacher@techniview.local", "password": "wrong"},
    )
    assert invalid.status_code == 401

    login = await client.post(
        "/api/auth/login",
        json={"email": "TEACHER@TECHNIVIEW.LOCAL", "password": "teacher-demo"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "professor"
    assert (await client.get("/api/auth/me")).status_code == 200

    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_problem_catalog_redacts_hidden_tests_and_start_is_idempotent(
    student_client, db_session
):
    listing = await student_client.get("/api/problems?difficulty=easy&tag=arrays")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    problem_id = listing.json()["items"][0]["id"]

    detail = await student_client.get(f"/api/problems/{problem_id}")
    assert detail.status_code == 200
    assert detail.json()["test_count"] == 2
    assert len(detail.json()["public_tests"]) == 1
    assert "[[-2, 2]]" not in detail.text

    assert (
        await student_client.post(f"/api/problems/{problem_id}/start")
    ).status_code == 204
    assert (
        await student_client.post(f"/api/problems/{problem_id}/start")
    ).status_code == 204
    count = db_session.scalar(select(func.count()).select_from(StudentPracticeProgress))
    assert count == 1


async def test_curriculum_unlocks_only_after_prerequisites(student_client):
    curriculum = await student_client.get("/api/curriculum")
    assert curriculum.status_code == 200
    assert [node["status"] for node in curriculum.json()] == ["completed", "available"]
    available = await student_client.get("/api/curriculum/available")
    assert [problem["title"] for problem in available.json()] == ["Count Evens"]


async def test_student_course_and_assignment_permissions(student_client):
    courses = (await student_client.get("/api/courses")).json()
    course_id = courses["items"][0]["id"]
    assert courses["items"][0]["membership_role"] == "student"
    assert (
        await student_client.get(f"/api/courses/{course_id}/members")
    ).status_code == 403

    assignments = await student_client.get(f"/api/courses/{course_id}/assignments")
    assert assignments.status_code == 200
    assert assignments.json()["total"] == 1
    assert len(assignments.json()["items"][0]["items"]) == 2

    second_item = assignments.json()["items"][0]["items"][1]
    started = await student_client.post(
        f"/api/problems/{second_item['problem']['id']}/start",
        params={"assignment_item_id": second_item["id"]},
    )
    assert started.status_code == 204


async def test_assignment_start_uses_a_separate_progress_context(
    student_client, db_session
):
    course_id = (await student_client.get("/api/courses")).json()["items"][0]["id"]
    assignment = (
        await student_client.get(f"/api/courses/{course_id}/assignments")
    ).json()["items"][0]
    second_item = assignment["items"][1]
    response = await student_client.post(
        f"/api/problems/{second_item['problem']['id']}/start",
        params={"assignment_item_id": second_item["id"]},
    )
    assert response.status_code == 204
    progress = db_session.get(
        StudentAssignmentProgress,
        ((await student_client.get("/api/auth/me")).json()["id"], second_item["id"]),
    )
    assert progress is not None
    assert progress.first_opened_at is not None


async def test_teacher_can_list_course_members(teacher_client):
    course_id = (await teacher_client.get("/api/courses")).json()["items"][0]["id"]
    members = await teacher_client.get(f"/api/courses/{course_id}/members")
    assert members.status_code == 200
    assert members.json()["total"] == 2


async def test_teacher_analytics_include_unfinished_recipients(teacher_client):
    course_id = (await teacher_client.get("/api/courses")).json()["items"][0]["id"]
    overview = await teacher_client.get(f"/api/courses/{course_id}/analytics/overview")
    assert overview.status_code == 200
    body = overview.json()
    assert body["total"] == 2
    assert body["summary"] == {
        "assigned_count": 2,
        "started_count": 1,
        "completed_count": 1,
        "completion_rate": 0.5,
        "avg_completion_seconds": 900.0,
        "median_completion_seconds": 900.0,
        "total_valid_attempts": 2,
        "total_retries": 1,
        "avg_retries_per_student": 0.5,
        "errors": {
            "wrong_answer": 1,
            "compile_error": 0,
            "runtime_error": 0,
            "timeout": 0,
            "resource_limit": 0,
        },
    }

    first = next(
        item for item in body["items"] if item["problem"]["title"] == "Sum a List"
    )
    problem_id = first["problem"]["id"]
    problem = await teacher_client.get(
        f"/api/courses/{course_id}/analytics/problems/{problem_id}"
    )
    assert problem.status_code == 200
    assert problem.json()["metrics"]["total_retries"] == 1

    members = (await teacher_client.get(f"/api/courses/{course_id}/members")).json()
    student_id = next(
        item["user_id"] for item in members["items"] if item["role"] == "student"
    )
    drilldown = await teacher_client.get(
        f"/api/courses/{course_id}/analytics/students/{student_id}"
        f"/problems/{problem_id}"
    )
    assert drilldown.status_code == 200
    assert drilldown.json()["metrics"]["avg_completion_seconds"] == 900.0


async def test_student_analytics_filter_by_problem_type_and_difficulty(
    student_client,
):
    all_metrics = (await student_client.get("/api/me/analytics")).json()["metrics"]
    assert all_metrics["assigned_count"] == 3
    assert all_metrics["completed_count"] == 2
    assert all_metrics["total_retries"] == 3

    filtered = (
        await student_client.get("/api/me/analytics?difficulty=medium&tag=loops")
    ).json()["metrics"]
    assert filtered["assigned_count"] == 1
    assert filtered["started_count"] == 0
    assert filtered["completion_rate"] == 0.0


async def test_analytics_count_repeated_unstarted_assignment_items(
    teacher_client, db_session
):
    instructor = db_session.scalar(
        select(CourseMembership).where(
            CourseMembership.role == MembershipRole.INSTRUCTOR
        )
    )
    student = db_session.scalar(
        select(CourseMembership).where(CourseMembership.role == MembershipRole.STUDENT)
    )
    problem = db_session.scalar(select(Problem).where(Problem.title == "Count Evens"))
    assignment = Assignment(
        course_id=instructor.course_id,
        assigned_by_membership_id=instructor.id,
        title="Repeated problem",
        state=AssignmentState.PUBLISHED,
    )
    db_session.add(assignment)
    db_session.flush()
    item = AssignmentItem(
        assignment_id=assignment.id,
        problem_id=problem.id,
        item_order=1,
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

    response = await teacher_client.get(
        f"/api/courses/{instructor.course_id}/analytics/overview"
    )
    repeated = next(
        row for row in response.json()["items"] if row["problem"]["id"] == problem.id
    )
    assert repeated["metrics"]["assigned_count"] == 2
