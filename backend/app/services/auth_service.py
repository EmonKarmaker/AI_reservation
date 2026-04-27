"""Auth service — business logic for register, login, refresh.

HTTP-agnostic. Functions raise custom exceptions; the auth router (Phase 1.7b)
translates them to ``HTTPException`` with appropriate status codes.

Token issuance also lives here so the router only worries about cookie
plumbing. Token decoding happens in ``app.core.permissions.get_current_user``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.enums import BusinessStatus, UserRole
from app.models.user import User


# ---------------------------------------------------------------------------
# Custom exceptions — caught by the auth router and mapped to HTTP errors
# ---------------------------------------------------------------------------

class AuthServiceError(Exception):
    """Base class for auth-service failures."""


class BusinessSlugTakenError(AuthServiceError):
    """Slug is already used by another business."""


class EmailAlreadyExistsError(AuthServiceError):
    """Email is already registered to a user."""


class InvalidCredentialsError(AuthServiceError):
    """Email/password combination is wrong, or the account is unusable.

    Raised for ALL of: missing user, wrong password, soft-deleted user,
    inactive user. Routers must NOT distinguish these — leaking which case
    applies enables account enumeration.
    """


class RefreshTokenError(AuthServiceError):
    """Refresh token is missing, invalid, expired, or the user is gone."""


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

async def register_business_with_admin(
    db: AsyncSession,
    *,
    business_name: str,
    business_slug: str,
    industry: str | None,
    timezone_name: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
) -> tuple[UUID, UUID]:
    """Create a Business + BusinessSetting + first business_admin User in one transaction.

    Returns ``(business_id, user_id)``. Raises ``BusinessSlugTakenError`` or
    ``EmailAlreadyExistsError`` if the corresponding unique constraint would
    be violated.

    The whole thing is one transaction: if the User INSERT fails, the
    Business and BusinessSetting rolls back too. The session yielded by
    ``get_db`` will commit at the end of the request.
    """
    # Pre-check uniqueness — gives nice 409s instead of generic 500s.
    # The DB-level unique constraint is the authoritative check; the IntegrityError
    # branch below catches the race where two simultaneous registrations both
    # pass the pre-check.
    slug_exists = await db.execute(
        select(Business.id).where(Business.slug == business_slug)
    )
    if slug_exists.scalar_one_or_none() is not None:
        raise BusinessSlugTakenError(business_slug)

    email_exists = await db.execute(
        select(User.id).where(User.email == admin_email)
    )
    if email_exists.scalar_one_or_none() is not None:
        raise EmailAlreadyExistsError(admin_email)

    business = Business(
        name=business_name,
        slug=business_slug,
        industry=industry,
        timezone=timezone_name,
        status=BusinessStatus.ACTIVE,
    )
    db.add(business)
    await db.flush()  # populate business.id

    settings_row = BusinessSetting(business_id=business.id)
    db.add(settings_row)

    user = User(
        email=admin_email,
        password_hash=hash_password(admin_password),
        full_name=admin_full_name,
        role=UserRole.BUSINESS_ADMIN,
        business_id=business.id,
    )
    db.add(user)

    try:
        await db.flush()  # populate user.id; surface unique-constraint races now
    except IntegrityError as exc:
        await db.rollback()
        # Distinguish which constraint blew up by sniffing the message.
        msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
        if "slug" in msg or "businesses" in msg:
            raise BusinessSlugTakenError(business_slug) from exc
        if "email" in msg or "users" in msg:
            raise EmailAlreadyExistsError(admin_email) from exc
        raise

    await db.commit()
    return business.id, user.id


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def authenticate_and_issue_tokens(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> tuple[User, str, str]:
    """Verify credentials, update last_login_at, return (user, access, refresh).

    Raises ``InvalidCredentialsError`` for ALL failure modes (missing user,
    wrong password, deleted, inactive). Do not distinguish — see the
    exception's docstring for why.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        raise InvalidCredentialsError()

    if user.deleted_at is not None or not user.is_active:
        raise InvalidCredentialsError()

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    user.last_login_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(user.id, user.role, user.business_id)
    refresh = create_refresh_token(user.id)
    return user, access, refresh


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

async def issue_new_access_token_from_refresh(
    db: AsyncSession,
    *,
    refresh_token: str | None,
) -> tuple[User, str]:
    """Decode a refresh token, fetch the user fresh from DB, issue a new access token.

    Returns ``(user, new_access_token)``. The refresh token is NOT rotated in
    v1 — token rotation is a v2 enhancement.

    Raises ``RefreshTokenError`` for missing cookie, bad/expired token, or
    user no longer eligible (deleted/inactive/missing).

    The user's role and business_id are read from the DB, NOT from the
    refresh token — refresh tokens deliberately don't carry that info, so
    role changes between login and refresh are reflected in the next access
    token.
    """
    if refresh_token is None:
        raise RefreshTokenError("Missing refresh token")

    try:
        claims = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise RefreshTokenError(str(exc)) from exc

    user_id_str = claims.get("sub")
    if not user_id_str:
        raise RefreshTokenError("Token missing subject")

    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise RefreshTokenError("Token subject is not a UUID") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.deleted_at is not None or not user.is_active:
        raise RefreshTokenError("User no longer eligible")

    new_access = create_access_token(user.id, user.role, user.business_id)
    return user, new_access
