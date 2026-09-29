from datetime import UTC

from fastapi import APIRouter, Response
from sqlalchemy import select

from ..core.config import settings
from ..core.dependencies import DbSession
from ..core.errors import ApiError
from ..core.security import (
    create_session,
    hash_password,
    hash_token,
    verify_password,
)
from ..models import Course, CourseMembership, MembershipRole, User, UserRole
from ..schemas.contracts import (
    JoinLoginRequest,
    JoinPreviewResponse,
    JoinSignupRequest,
    UserResponse,
)

router = APIRouter(prefix="/join", tags=["join"])


def _course_by_token(db, token: str) -> Course:
    course = db.scalar(select(Course).where(Course.join_code_hash == hash_token(token)))
    if course is None:
        raise ApiError(404, "join_link_not_found", "Join link not found.")
    return course


def _enroll(db, course: Course, user: User) -> CourseMembership:
    # Flush-only: the caller owns the commit so user-create + enroll land in
    # one transaction. Reactivation restores access without changing privilege;
    # the student link never grants or strips roles.
    membership = db.scalar(
        select(CourseMembership).where(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == user.id,
        )
    )
    if membership is not None:
        if membership.withdrawn_at is not None:
            membership.withdrawn_at = None
            db.flush()
        return membership
    membership = CourseMembership(
        course_id=course.id,
        user_id=user.id,
        role=MembershipRole.STUDENT,
    )
    db.add(membership)
    db.flush()
    return membership


def _set_session_cookie(response: Response, db, user: User) -> None:
    token, session = create_session(db, user)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        expires=session.expires_at.replace(tzinfo=UTC),
        path="/",
    )


@router.get("/{token}", response_model=JoinPreviewResponse)
def join_preview(token: str, db: DbSession):
    course = _course_by_token(db, token)
    return {
        "course_id": course.id,
        "name": course.name,
        "description": course.description,
        "joinable": course.archived_at is None,
    }


@router.post("/{token}/signup", response_model=UserResponse)
def join_signup(token: str, body: JoinSignupRequest, response: Response, db: DbSession):
    course = _course_by_token(db, token)
    if course.archived_at is not None:
        raise ApiError(409, "course_archived", "This class is archived and closed.")
    if body.password != body.password_confirm:
        raise ApiError(422, "password_mismatch", "Passwords do not match.")
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name:
        raise ApiError(422, "invalid_name", "Name must not be blank.")
    if not email:
        raise ApiError(422, "invalid_email", "Email must not be blank.")
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiError(
            409,
            "email_exists",
            "An account with this email already exists. Log in instead.",
        )
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(body.password),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()
    _enroll(db, course, user)
    db.commit()
    db.refresh(user)
    _set_session_cookie(response, db, user)
    return user


@router.post("/{token}/login", response_model=UserResponse)
def join_login(token: str, body: JoinLoginRequest, response: Response, db: DbSession):
    course = _course_by_token(db, token)
    if course.archived_at is not None:
        raise ApiError(409, "course_archived", "This class is archived and closed.")
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or user.disabled_at is not None
        or not verify_password(body.password, user.password_hash)
    ):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    _enroll(db, course, user)
    db.commit()
    _set_session_cookie(response, db, user)
    return user
