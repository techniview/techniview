from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.models import (
    AssignmentAudit,
    AssignmentRecipient,
    CourseMembership,
    StudentAssignmentProgress,
    User,
    UserRole,
)
from sqlalchemy import select

pytestmark = pytest.mark.anyio


async def _context(teacher_client, db):
    course = (await teacher_client.get("/api/courses")).json()["items"][0]
    student = db.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course["id"],
            CourseMembership.role == "student",
        )
    )
    problems = (await teacher_client.get("/api/problems")).json()["items"]
    return course["id"], student, problems[0]["id"]


async def test_publication_snapshots_recipients_and_freezes_items(
    teacher_client,
    student_client,
    db_session,
):
    course_id, student, problem_id = await _context(teacher_client, db_session)
    created = await teacher_client.post(
        f"/api/courses/{course_id}/assignments",
        json={
            "title": "Snapshot test",
            "items": [
                {"problem_id": problem_id, "points": "7.5", "submission_limit": 2}
            ],
            "recipient_mode": "all",
        },
    )
    assert created.status_code == 201, created.text
    aid = created.json()["id"]
    assert db_session.get(AssignmentRecipient, (aid, student.id)) is None
    new_user = User(
        name="Later student",
        email="later@example.test",
        password_hash="unused",
        role=UserRole.STUDENT,
        email_verified_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(new_user)
    db_session.flush()
    db_session.add(
        CourseMembership(course_id=course_id, user_id=new_user.id, role="student")
    )
    db_session.commit()
    published = await teacher_client.post(
        f"/api/courses/{course_id}/assignments/{aid}/publish"
    )
    assert published.status_code == 200, published.text
    assert Decimal(published.json()["items"][0]["points"]) == Decimal("7.5")
    assert published.json()["items"][0]["submission_limit"] == 2
    rows = db_session.scalars(
        select(AssignmentRecipient).where(AssignmentRecipient.assignment_id == aid)
    ).all()
    assert len(rows) == 2
    another = User(
        name="After publication",
        email="after@example.test",
        password_hash="unused",
        role=UserRole.STUDENT,
        email_verified_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(another)
    db_session.flush()
    db_session.add(
        CourseMembership(course_id=course_id, user_id=another.id, role="student")
    )
    db_session.commit()
    assert (
        len(
            db_session.scalars(
                select(AssignmentRecipient).where(
                    AssignmentRecipient.assignment_id == aid
                )
            ).all()
        )
        == 2
    )
    frozen = await teacher_client.patch(
        f"/api/courses/{course_id}/assignments/{aid}",
        json={"items": [{"problem_id": problem_id, "points": 99}]},
    )
    assert frozen.status_code == 409
    due_at = (datetime.now(UTC) + timedelta(days=10)).isoformat()
    changed = await teacher_client.patch(
        f"/api/courses/{course_id}/assignments/{aid}", json={"due_at": due_at}
    )
    assert changed.status_code == 200
    assert (
        db_session.scalar(
            select(AssignmentAudit).where(
                AssignmentAudit.assignment_id == aid, AssignmentAudit.action == "edit"
            )
        )
        is not None
    )


async def test_removed_recipient_loses_access_but_keeps_progress(
    teacher_client,
    student_client,
    db_session,
):
    course_id, student, problem_id = await _context(teacher_client, db_session)
    created = await teacher_client.post(
        f"/api/courses/{course_id}/assignments",
        json={
            "title": "Recipient test",
            "items": [{"problem_id": problem_id}],
            "recipient_mode": "selected",
            "selected_membership_ids": [student.id],
        },
    )
    aid = created.json()["id"]
    await teacher_client.post(f"/api/courses/{course_id}/assignments/{aid}/publish")
    item_id = created.json()["items"][0]["id"]
    db_session.add(
        StudentAssignmentProgress(
            student_id=student.user_id,
            assignment_item_id=item_id,
            best_score=Decimal("0.5"),
            first_opened_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    db_session.commit()
    removed = await teacher_client.post(
        f"/api/courses/{course_id}/assignments/{aid}/recipients",
        json={"remove_membership_ids": [student.id]},
    )
    assert removed.status_code == 204, removed.text
    assert db_session.get(AssignmentRecipient, (aid, student.id)).removed_at is not None
    assert db_session.get(
        StudentAssignmentProgress, (student.user_id, item_id)
    ).best_score == Decimal("0.5")
    assert (
        await student_client.get(f"/api/courses/{course_id}/assignments/{aid}")
    ).status_code == 404
    submission = await student_client.post(
        "/api/submissions",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "problem_id": problem_id,
            "assignment_item_id": item_id,
            "source_code": "pass",
        },
    )
    assert submission.status_code == 404
    restored = await teacher_client.post(
        f"/api/courses/{course_id}/assignments/{aid}/recipients",
        json={"add_membership_ids": [student.id]},
    )
    assert restored.status_code == 204
    assert db_session.get(AssignmentRecipient, (aid, student.id)).removed_at is None
    audits = (
        await teacher_client.get(f"/api/courses/{course_id}/assignments/{aid}/audit")
    ).json()
    assert audits["total"] == 3
