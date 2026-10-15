from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response
from sqlalchemy import select

from ..core.config import settings
from ..core.dependencies import CurrentUser, DbSession
from ..core.errors import ApiError
from ..core.security import (
    create_session,
    hash_token,
    verify_password,
)
from ..models import User, UserSession
from ..schemas.contracts import LoginRequest, UserResponse
from ..schemas.course_management import (
    EmailVerificationRequest,
    PasswordRecoveryRequest,
    PasswordResetRequest,
)
from ..services.account_recovery import (
    request_password_reset,
    reset_password,
    verify_email,
)
from ..services.account_throttle import throttle_account_request

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: DbSession):
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
    return user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: DbSession,
    session_token: Annotated[
        str | None, Cookie(alias=settings.SESSION_COOKIE_NAME)
    ] = None,
):
    if session_token:
        session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_token(session_token),
                UserSession.revoked_at.is_(None),
            )
        )
        if session is not None:
            session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return user


@router.post("/password-recovery", status_code=202)
def recover_password(body: PasswordRecoveryRequest, db: DbSession, request: Request):
    throttle_account_request(
        db, "recovery", request.client.host if request.client else "unknown"
    )
    request_password_reset(db, body.email)
    return {
        "message": "If the account is eligible, a password reset link will be sent."
    }


@router.post("/password-reset", status_code=204)
def change_password(body: PasswordResetRequest, db: DbSession, response: Response):
    if body.password != body.password_confirm:
        raise ApiError(422, "password_mismatch", "Passwords do not match.")
    reset_password(db, body.token, body.password)
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")


@router.post("/verify-email", response_model=UserResponse)
def confirm_email(body: EmailVerificationRequest, db: DbSession):
    return verify_email(db, body.token)
