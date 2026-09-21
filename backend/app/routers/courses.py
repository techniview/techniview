from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.authorization import get_membership
from ..core.dependencies import CurrentUser, DbSession, InstructorMembership
from ..core.errors import ApiError
from ..models import Course, CourseMembership, User
from ..schemas.contracts import (
    CourseListResponse,
    CourseResponse,
    MemberListResponse,
    MemberResponse,
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
    _membership: InstructorMembership,
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
