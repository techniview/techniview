from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..core.authorization import get_membership
from ..core.dependencies import (
    CurrentUser,
    DbSession,
    InstructorMembership,
    StaffMembership,
)
from ..core.errors import ApiError
from ..models import (
    Assignment,
    AssignmentItem,
    AssignmentRecipient,
    Course,
    CourseMembership,
    MembershipRole,
    StudentAssignmentProgress,
    Submission,
    SubmissionCaseResult,
    User,
)
from ..schemas.contracts import (
    CourseListResponse,
    CourseResponse,
    MemberListResponse,
    MemberResponse,
    MemberRoleUpdateRequest,
)

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=CourseListResponse)
def list_courses(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    base = (
        select(CourseMembership)
        .options(selectinload(CourseMembership.course))
        .where(
            CourseMembership.user_id == user.id,
            CourseMembership.withdrawn_at.is_(None),
        )
        .order_by(CourseMembership.joined_at.desc())
    )
    memberships = list(db.scalars(base).all())
    items = [
        CourseResponse.model_validate(
            {**membership.course.__dict__, "membership_role": membership.role}
        )
        for membership in memberships[offset : offset + limit]
    ]
    return {"items": items, "total": len(memberships), "limit": limit, "offset": offset}


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: int,
    db: DbSession,
    user: CurrentUser,
):
    membership = get_membership(db, course_id, user.id)
    course = db.get(Course, course_id)
    if course is None:
        raise ApiError(404, "course_not_found", "Course not found.")
    return {**course.__dict__, "membership_role": membership.role}


@router.get("/{course_id}/members", response_model=MemberListResponse)
def list_members(
    course_id: int,
    db: DbSession,
    _membership: StaffMembership,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    rows = list(
        db.execute(
            select(CourseMembership, User)
            .join(User, User.id == CourseMembership.user_id)
            .where(CourseMembership.course_id == course_id)
            .order_by(User.name, User.id)
        ).all()
    )
    items = [
        MemberResponse(
            id=membership.id,
            user_id=member.id,
            name=member.name,
            email=member.email,
            role=membership.role,
            joined_at=membership.joined_at,
            withdrawn_at=membership.withdrawn_at,
        )
        for membership, member in rows[offset : offset + limit]
    ]
    return {"items": items, "total": len(rows), "limit": limit, "offset": offset}


def _member_or_404(
    db, course_id: int, membership_id: int, *, include_withdrawn: bool = False
) -> CourseMembership:
    membership = db.get(CourseMembership, membership_id)
    if membership is None or membership.course_id != course_id:
        raise ApiError(404, "member_not_found", "Member not found.")
    if not include_withdrawn and membership.withdrawn_at is not None:
        raise ApiError(404, "member_not_found", "Member not found.")
    return membership


def _guard_last_instructor(db, course_id: int, target: CourseMembership) -> None:
    if target.role != MembershipRole.INSTRUCTOR:
        return
    remaining = db.scalar(
        select(func.count())
        .select_from(CourseMembership)
        .where(
            CourseMembership.course_id == course_id,
            CourseMembership.role == MembershipRole.INSTRUCTOR,
            CourseMembership.withdrawn_at.is_(None),
            CourseMembership.id != target.id,
        )
    )
    if not remaining:
        raise ApiError(
            409, "last_instructor", "Cannot remove or demote the last instructor."
        )


def _member_response(db, membership: CourseMembership) -> MemberResponse:
    member = db.get(User, membership.user_id)
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        name=member.name if member else "",
        email=member.email if member else "",
        role=membership.role,
        joined_at=membership.joined_at,
        withdrawn_at=membership.withdrawn_at,
    )


@router.patch("/{course_id}/members/{membership_id}", response_model=MemberResponse)
def update_member_role(
    course_id: int,
    membership_id: int,
    body: MemberRoleUpdateRequest,
    db: DbSession,
    _membership: InstructorMembership,
):
    target = _member_or_404(db, course_id, membership_id)
    if (
        target.role == MembershipRole.INSTRUCTOR
        and body.role != MembershipRole.INSTRUCTOR
    ):
        _guard_last_instructor(db, course_id, target)
    target.role = body.role
    db.commit()
    db.refresh(target)
    return _member_response(db, target)


@router.delete("/{course_id}/members/{membership_id}", status_code=204)
def remove_member(
    course_id: int,
    membership_id: int,
    db: DbSession,
    _membership: InstructorMembership,
):
    target = _member_or_404(db, course_id, membership_id, include_withdrawn=True)
    if target.withdrawn_at is None:
        _guard_last_instructor(db, course_id, target)
    user_id = target.user_id
    authored = db.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(
            Assignment.course_id == course_id,
            Assignment.assigned_by_membership_id == target.id,
        )
    )
    if authored:
        raise ApiError(
            409,
            "member_authored_assignments",
            "Cannot remove a member who created assignments in this class.",
        )

    item_ids = list(
        db.scalars(
            select(AssignmentItem.id)
            .join(Assignment, Assignment.id == AssignmentItem.assignment_id)
            .where(Assignment.course_id == course_id)
        ).all()
    )
    if item_ids:
        db.query(StudentAssignmentProgress).filter(
            StudentAssignmentProgress.student_id == user_id,
            StudentAssignmentProgress.assignment_item_id.in_(item_ids),
        ).delete(synchronize_session=False)
        submission_ids = list(
            db.scalars(
                select(Submission.id).where(
                    Submission.student_id == user_id,
                    Submission.assignment_item_id.in_(item_ids),
                )
            ).all()
        )
        if submission_ids:
            db.query(SubmissionCaseResult).filter(
                SubmissionCaseResult.submission_id.in_(submission_ids)
            ).delete(synchronize_session=False)
            db.query(Submission).filter(Submission.id.in_(submission_ids)).delete(
                synchronize_session=False
            )
    db.query(AssignmentRecipient).filter(
        AssignmentRecipient.membership_id == target.id,
        AssignmentRecipient.course_id == course_id,
    ).delete(synchronize_session=False)
    db.delete(target)
    db.commit()
