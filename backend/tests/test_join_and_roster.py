import pytest
from app.models import CourseMembership, MembershipRole
from app.seed import DEMO_COURSE_JOIN_TOKEN
from sqlalchemy import func, select

pytestmark = pytest.mark.anyio

JOIN = f"/api/join/{DEMO_COURSE_JOIN_TOKEN}"


async def test_join_preview_is_public(client):
    response = await client.get(JOIN)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "CS 101 Demo"
    assert body["joinable"] is True


async def test_join_invalid_token_404(client):
    response = await client.get("/api/join/nope-not-real")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "join_link_not_found"


async def test_join_signup_and_login_variants_are_idempotent(client, db_session):
    signup = await client.post(
        f"{JOIN}/signup",
        json={
            "name": "New Kid",
            "email": "NewKid@Techniview.Local",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert signup.status_code == 200
    assert signup.json()["email"] == "newkid@techniview.local"
    assert signup.json()["role"] == "student"

    # Same link again via login variant: no duplicate membership.
    login = await client.post(
        f"{JOIN}/login",
        json={"email": "newkid@techniview.local", "password": "password123"},
    )
    assert login.status_code == 200
    count = db_session.scalar(
        select(func.count())
        .select_from(CourseMembership)
        .where(CourseMembership.course_id == 1)
        .where(
            CourseMembership.user_id.in_(
                select(CourseMembership.user_id).where(CourseMembership.course_id == 1)
            )
        )
    )
    assert count is not None
    user_memberships = db_session.scalars(
        select(CourseMembership).where(
            CourseMembership.course_id == 1,
            CourseMembership.user_id == login.json()["id"],
        )
    ).all()
    assert len(user_memberships) == 1


async def test_join_signup_existing_email_points_to_login(client):
    response = await client.post(
        f"{JOIN}/signup",
        json={
            "name": "Dup",
            "email": "student@techniview.local",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_exists"


async def test_join_signup_password_mismatch(client):
    response = await client.post(
        f"{JOIN}/signup",
        json={
            "name": "Mismatch",
            "email": "mismatch@techniview.local",
            "password": "password123",
            "password_confirm": "different456",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "password_mismatch"


async def _login(client, email, password):
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    return response


async def test_instructor_can_promote_to_ta_and_student_cannot(client, db_session):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")

    promoted = await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ta"
    assert db_session.get(CourseMembership, student_row["id"]).role == MembershipRole.TA

    await _login(client, "student@techniview.local", "student-demo")
    forbidden = await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "student"},
    )
    assert forbidden.status_code in (401, 403)


async def test_ta_keeps_read_access_but_cannot_manage(client, db_session):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    await _login(client, "student@techniview.local", "student-demo")
    assert (await client.get(f"/api/courses/{course_id}/members")).status_code == 200
    assert (
        await client.get(f"/api/courses/{course_id}/analytics/overview")
    ).status_code == 200
    assert (
        await client.delete(f"/api/courses/{course_id}/members/{student_row['id']}")
    ).status_code == 403


async def test_instructor_hard_erase_removes_class_data(client, db_session):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    await _login(client, "student@techniview.local", "student-demo")
    me = (await client.get("/api/auth/me")).json()
    await _login(client, "teacher@techniview.local", "teacher-demo")
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["user_id"] == me["id"])
    response = await client.delete(
        f"/api/courses/{course_id}/members/{student_row['id']}"
    )
    assert response.status_code == 204
    assert db_session.get(CourseMembership, student_row["id"]) is None
    # Seeded student had assignment progress + recipient rows: both gone.
    from app.models import AssignmentRecipient, StudentAssignmentProgress

    assert (
        db_session.scalar(
            select(func.count())
            .select_from(AssignmentRecipient)
            .where(AssignmentRecipient.membership_id == student_row["id"])
        )
        == 0
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(StudentAssignmentProgress)
            .where(StudentAssignmentProgress.student_id == me["id"])
        )
        == 0
    )


async def test_join_signup_blank_name_rejected(client):
    response = await client.post(
        f"{JOIN}/signup",
        json={
            "name": "   ",
            "email": "blank@techniview.local",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_name"


async def test_cannot_remove_member_who_authored_assignments(client, db_session):
    from app.models import Assignment, AssignmentState

    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    instructor_row = next(
        item for item in members["items"] if item["role"] == "instructor"
    )
    assignment = Assignment(
        course_id=course_id,
        assigned_by_membership_id=instructor_row["id"],
        title="Authored",
        state=AssignmentState.DRAFT,
    )
    db_session.add(assignment)
    db_session.commit()
    # Add a second instructor so the last-instructor guard passes and the
    # authored-assignments guard is the one under test.
    student_row = next(item for item in members["items"] if item["role"] == "student")
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "instructor"},
    )
    response = await client.delete(
        f"/api/courses/{course_id}/members/{instructor_row['id']}"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "member_authored_assignments"


async def test_ta_sees_staff_problems_in_listing(client, db_session):
    from app.models import Assignment, AssignmentItem, AssignmentState, Problem

    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    problem = db_session.scalar(select(Problem).where(Problem.title == "Sum a List"))
    hidden_assignment = Assignment(
        course_id=course_id,
        assigned_by_membership_id=next(
            item["id"] for item in members["items"] if item["role"] == "instructor"
        ),
        title="Staff only view",
        state=AssignmentState.PUBLISHED,
    )
    db_session.add(hidden_assignment)
    db_session.flush()
    db_session.add(
        AssignmentItem(
            assignment_id=hidden_assignment.id,
            problem_id=problem.id,
            item_order=1,
        )
    )
    db_session.commit()
    await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    await _login(client, "student@techniview.local", "student-demo")
    listing = await client.get("/api/problems")
    assert listing.status_code == 200
    assert problem.id in [item["id"] for item in listing.json()["items"]]


async def test_rejoin_reactivates_without_changing_role(client, db_session):
    from datetime import UTC, datetime

    from app.models import User

    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    membership = db_session.get(CourseMembership, student_row["id"])
    membership.role = MembershipRole.TA
    membership.withdrawn_at = datetime.now(UTC).replace(tzinfo=None)
    db_session.commit()
    user = db_session.get(User, membership.user_id)

    response = await client.post(
        f"{JOIN}/login",
        json={"email": user.email, "password": "student-demo"},
    )
    assert response.status_code == 200
    reactivated = db_session.get(CourseMembership, student_row["id"])
    assert reactivated.withdrawn_at is None
    assert reactivated.role == MembershipRole.TA


async def test_patch_withdrawn_member_404s(client, db_session):
    from datetime import UTC, datetime

    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    student_row = next(item for item in members["items"] if item["role"] == "student")
    membership = db_session.get(CourseMembership, student_row["id"])
    membership.withdrawn_at = datetime.now(UTC).replace(tzinfo=None)
    db_session.commit()
    response = await client.patch(
        f"/api/courses/{course_id}/members/{student_row['id']}",
        json={"role": "ta"},
    )
    assert response.status_code == 404


async def test_cannot_remove_last_instructor(client):
    await _login(client, "teacher@techniview.local", "teacher-demo")
    course_id = (await client.get("/api/courses")).json()["items"][0]["id"]
    members = (await client.get(f"/api/courses/{course_id}/members")).json()
    instructor_row = next(
        item for item in members["items"] if item["role"] == "instructor"
    )
    response = await client.delete(
        f"/api/courses/{course_id}/members/{instructor_row['id']}"
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_instructor"
