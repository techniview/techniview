import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from ..core.authorization import get_membership, require_active_course
from ..core.dependencies import (
    CurrentUser,
    DbSession,
    InstructorMembership,
    StaffMembership,
)
from ..core.errors import ApiError
from ..core.security import hash_token
from ..models import (
    AccountToken,
    Course,
    CourseEnrollment,
    CourseMembership,
    MembershipRole,
    User,
    UserRole,
)
from ..schemas.contracts import (
    CourseListResponse,
    CourseResponse,
    MemberListResponse,
    MemberResponse,
    MemberRoleUpdateRequest,
)
from ..schemas.course_management import (
    CourseCreateRequest,
    CourseUpdateRequest,
    CsvEnrollmentRequest,
)
from ..services.enrollment import import_enrollment_csv

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
        )
        .order_by(
            CourseMembership.withdrawn_at.is_not(None),
            CourseMembership.joined_at.desc(),
            CourseMembership.id.desc(),
        )
    )
    memberships = list(db.scalars(base).all())
    items = [
        CourseResponse.model_validate(
            {
                **membership.course.__dict__,
                "membership_role": membership.role,
                "withdrawn_at": membership.withdrawn_at,
            }
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
    membership = get_membership(db, course_id, user.id, include_withdrawn=True)
    course = db.get(Course, course_id)
    if course is None:
        raise ApiError(404, "course_not_found", "Course not found.")
    return {
        **course.__dict__,
        "membership_role": membership.role,
        "withdrawn_at": membership.withdrawn_at,
    }


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
    require_active_course(db, course_id)
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
    require_active_course(db, course_id)
    target = _member_or_404(db, course_id, membership_id, include_withdrawn=True)
    if target.withdrawn_at is None:
        _guard_last_instructor(db, course_id, target)
        target.withdrawn_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()


@router.post("", status_code=201)
def create_course(body: CourseCreateRequest, db: DbSession, user: CurrentUser):
    if user.role != UserRole.PROFESSOR:
        raise ApiError(403, "instructor_required", "Instructor access is required.")
    token = secrets.token_urlsafe(32)
    course = Course(**body.model_dump(), join_code_hash=hash_token(token))
    db.add(course)
    db.flush()
    db.add(
        CourseMembership(
            course_id=course.id, user_id=user.id, role=MembershipRole.INSTRUCTOR
        )
    )
    db.commit()
    db.refresh(course)
    return {
        "course": CourseResponse.model_validate(
            {
                **course.__dict__,
                "membership_role": MembershipRole.INSTRUCTOR,
                "withdrawn_at": None,
            }
        ),
        "join_token": token,
    }


@router.put("/{course_id}", response_model=CourseResponse)
def update_course(
    course_id: int,
    body: CourseUpdateRequest,
    db: DbSession,
    membership: InstructorMembership,
):
    course = require_active_course(db, course_id)
    for key, value in body.model_dump().items():
        setattr(course, key, value)
    db.commit()
    return {
        **course.__dict__,
        "membership_role": membership.role,
        "withdrawn_at": membership.withdrawn_at,
    }


@router.post("/{course_id}/archive", response_model=CourseResponse)
def archive_course(course_id: int, db: DbSession, membership: InstructorMembership):
    course = db.scalar(select(Course).where(Course.id == course_id).with_for_update())
    if course.archived_at is None:
        course.archived_at = datetime.now(UTC).replace(tzinfo=None)
    db.commit()
    return {
        **course.__dict__,
        "membership_role": membership.role,
        "withdrawn_at": membership.withdrawn_at,
    }


@router.post("/{course_id}/join-link")
def rotate_join_link(course_id: int, db: DbSession, _membership: InstructorMembership):
    course = require_active_course(db, course_id)
    token = secrets.token_urlsafe(32)
    course.join_code_hash = hash_token(token)
    db.commit()
    return {"join_token": token}


@router.post("/{course_id}/enrollments/import")
def import_enrollments(
    course_id: int,
    body: CsvEnrollmentRequest,
    db: DbSession,
    _membership: InstructorMembership,
):
    require_active_course(db, course_id)
    result = import_enrollment_csv(db, course_id, body.csv)
    db.commit()
    return result


@router.get("/{course_id}/enrollments")
def list_pending_enrollments(
    course_id: int,
    db: DbSession,
    _membership: StaffMembership,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    query = select(CourseEnrollment).where(CourseEnrollment.course_id == course_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(CourseEnrollment.id).offset(offset).limit(limit)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "email": row.email,
                "name": row.name,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/{course_id}/enrollments/{enrollment_id}", status_code=204)
def cancel_pending_enrollment(
    course_id: int, enrollment_id: int, db: DbSession, _membership: InstructorMembership
):
    require_active_course(db, course_id)
    enrollment = db.get(CourseEnrollment, enrollment_id)
    if enrollment is None or enrollment.course_id != course_id:
        raise ApiError(404, "enrollment_not_found", "Pending enrollment not found.")
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.course_id == course_id,
            AccountToken.purpose == "verify",
            AccountToken.user_id.in_(
                select(User.id).where(User.email == enrollment.email)
            ),
            AccountToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC).replace(tzinfo=None))
    )
    db.delete(enrollment)
    db.commit()
