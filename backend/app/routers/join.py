from datetime import UTC

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from ..core.authorization import require_active_course
from ..core.config import settings
from ..core.dependencies import DbSession
from ..core.errors import ApiError
from ..core.security import (
    create_session,
    hash_password,
    hash_token,
    verify_password,
)
from ..models import Course, CourseEnrollment, User, UserRole
from ..schemas.contracts import (
    JoinLoginRequest,
    JoinPreviewResponse,
    JoinSignupRequest,
    UserResponse,
)
from ..services.account_recovery import issue_account_token, require_email_delivery
from ..services.account_throttle import throttle_account_request
from ..services.enrollment import EMAIL_PATTERN, enroll_student

router = APIRouter(prefix="/join", tags=["join"])


def _course_by_token(db, token: str, email: str | None = None) -> Course:
    course = db.scalar(select(Course).where(Course.join_code_hash == hash_token(token)))
    if course is None:
        enrollment = db.scalar(
            select(CourseEnrollment).where(
                CourseEnrollment.token_hash == hash_token(token)
            )
        )
        if enrollment is not None and (
            email is None or email.strip().lower() == enrollment.email
        ):
            course = db.get(Course, enrollment.course_id)
    if course is None:
        raise ApiError(404, "join_link_not_found", "Join link not found.")
    return course


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


@router.post("/{token}/signup", status_code=202)
def join_signup(
    token: str,
    body: JoinSignupRequest,
    response: Response,
    db: DbSession,
    request: Request,
):
    throttle_account_request(
        db, "join", request.client.host if request.client else "unknown"
    )
    course = _course_by_token(db, token, body.email)
    require_active_course(db, course.id)
    if body.password != body.password_confirm:
        raise ApiError(422, "password_mismatch", "Passwords do not match.")
    name = body.name.strip()
    email = body.email.strip().lower()
    if not name:
        raise ApiError(422, "invalid_name", "Name must not be blank.")
    if not EMAIL_PATTERN.fullmatch(email):
        raise ApiError(422, "invalid_email", "Enter a valid email address.")
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise ApiError(
            409,
            "email_exists",
            "An account with this email already exists. Log in instead.",
        )
    require_email_delivery()
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(body.password),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()
    issue_account_token(db, user, "verify", course.id)
    db.commit()
    return {"message": "Check your email to verify your account and join the class."}


@router.post("/{token}/login")
def join_login(
    token: str,
    body: JoinLoginRequest,
    response: Response,
    db: DbSession,
    request: Request,
):
    throttle_account_request(
        db, "join", request.client.host if request.client else "unknown"
    )
    course = _course_by_token(db, token, body.email)
    require_active_course(db, course.id)
    email = body.email.strip().lower()
    user = db.scalar(
        select(User)
        .where(User.email == email)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.disabled_at is not None
        or not verify_password(body.password, user.password_hash)
    ):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if user.email_verified_at is None:
        issue_account_token(db, user, "verify", course.id)
        db.commit()
        response.status_code = 202
        return {
            "message": "Check your email to verify your account and join the class."
        }
    enroll_student(db, course.id, user)
    db.commit()
    _set_session_cookie(response, db, user)
    return UserResponse.model_validate(user)
