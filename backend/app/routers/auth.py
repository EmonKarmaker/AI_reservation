"""Auth router — 5 endpoints per docs/03-api.md section 1.

POST /auth/register   public, 201 Created
POST /auth/login      public, sets cookies
POST /auth/logout     public, clears cookies, 204 No Content
POST /auth/refresh    uses refresh cookie, re-issues access cookie
GET  /auth/me         JWT required

Cookie strategy:
- ``access_token``  — short-lived (15m), httpOnly, samesite=lax
- ``refresh_token`` — long-lived (7d), httpOnly, samesite=lax
- ``secure=True`` only in prod/staging — local dev is HTTP, browsers
  reject ``Secure`` cookies over HTTP.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.permissions import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    get_current_user,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    UserOut,
)
from app.services.auth_service import (
    BusinessSlugTakenError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    RefreshTokenError,
    authenticate_and_issue_tokens,
    issue_new_access_token_from_refresh,
    register_business_with_admin,
)


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

_ACCESS_TOKEN_MAX_AGE_SECONDS = settings.JWT_ACCESS_EXPIRE_MINUTES * 60
_REFRESH_TOKEN_MAX_AGE_SECONDS = settings.JWT_REFRESH_EXPIRE_DAYS * 24 * 60 * 60


def _cookie_secure_flag() -> bool:
    """Return True only in deployed environments where HTTPS is enforced."""
    return settings.ENVIRONMENT in {"prod", "staging"}


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        max_age=_ACCESS_TOKEN_MAX_AGE_SECONDS,
        httponly=True,
        secure=_cookie_secure_flag(),
        samesite="lax",
        path="/",
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=token,
        max_age=_REFRESH_TOKEN_MAX_AGE_SECONDS,
        httponly=True,
        secure=_cookie_secure_flag(),
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a business and its first admin user",
)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterResponse:
    try:
        business_id, user_id = await register_business_with_admin(
            db,
            business_name=body.business_name,
            business_slug=body.business_slug,
            industry=body.industry,
            timezone_name=body.timezone,
            admin_email=body.admin_email,
            admin_password=body.admin_password,
            admin_full_name=body.admin_full_name,
        )
    except BusinessSlugTakenError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Business slug already taken",
        ) from exc
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    return RegisterResponse(business_id=business_id, user_id=user_id)


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate and issue auth cookies",
)
async def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    try:
        user, access, refresh = await authenticate_and_issue_tokens(
            db,
            email=body.email,
            password=body.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc

    _set_access_cookie(response, access)
    _set_refresh_cookie(response, refresh)
    return LoginResponse(user=UserOut.model_validate(user))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear auth cookies",
)
async def logout(response: Response) -> Response:
    """Logout is idempotent — succeeds whether the caller had cookies or not.

    Returns 204 No Content. The Response object is the place to attach the
    cookie deletions; FastAPI will use it as the actual response.
    """
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/refresh",
    response_model=LoginResponse,
    summary="Issue a new access token from the refresh cookie",
)
async def refresh(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)] = None,
) -> LoginResponse:
    try:
        user, new_access = await issue_new_access_token_from_refresh(
            db,
            refresh_token=refresh_token,
        )
    except RefreshTokenError as exc:
        # Wipe potentially-stale cookies on 401 — the client should re-login.
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc

    _set_access_cookie(response, new_access)
    return LoginResponse(user=UserOut.model_validate(user))


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Return the current authenticated user",
)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    return MeResponse(user=UserOut.model_validate(user))
