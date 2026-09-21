from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CourseMembership, MembershipRole, User
from .db import get_db
from .errors import ApiError
from .security import get_current_user


def get_membership(db: Session, course_id: int, user_id: int) -> CourseMembership:
    membership = db.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course_id,
            CourseMembership.user_id == user_id,
            CourseMembership.withdrawn_at.is_(None),
        )
    )
    if membership is None:
        raise ApiError(404, "course_not_found", "Course not found.")
    return membership


def require_instructor(
    course_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CourseMembership:
    membership = get_membership(db, course_id, user.id)
    if membership.role != MembershipRole.INSTRUCTOR:
        raise ApiError(403, "instructor_required", "Instructor access is required.")
    return membership
