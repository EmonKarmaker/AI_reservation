"""FastAPI permission dependencies.

Three dependencies that gate endpoints by role, plus one helper that resolves
the business-scope filter for queries.

- ``get_current_user`` — extract JWT from cookie, decode, load user from DB.
  Used by every protected endpoint. Raises 401 on bad/missing/expired token,
  or when the user is missing/deleted/inactive.

- ``require_super_admin`` — gates super-admin-only endpoints (``/super/*``).
  Raises 403 if the user is not a super_admin.

- ``require_business_admin`` — gates business-admin endpoints (``/admin/*``).
  Both ``business_admin`` and ``super_admin`` pass; super admins can act on
  any business endpoint per docs/03-api.md.

- ``get_business_id_filter`` — returns the ``business_id`` to scope queries by.
  Returns the user's own ``business_id`` for business admins, ``None`` for
  super admins (meaning "no filter; see everything"). Routers AND'/' this into
  WHERE clauses on business-scoped tables.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenError, decode_token
from app.models.enums import UserRole
from app.models.user import User


# Cookie names — kept here so ``permissions.py`` and the auth router (Phase 1.7)
# share a single source of truth.
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)


async def get_current_user(
    access_token: Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Load the User identified by the access-token cookie.

    Raises ``HTTPException(401)`` for any failure mode — missing cookie,
    invalid signature, expired token, wrong token type, user not found,
    user deleted, or user inactive. We do not distinguish between these
    cases in the response so attackers cannot use the error messages
    to enumerate accounts or token states.
    """
    if access_token is None:
        raise _INVALID_CREDENTIALS

    try:
        claims = decode_token(access_token, expected_type="access")
    except TokenError as exc:
        raise _INVALID_CREDENTIALS from exc

    user_id_str = claims.get("sub")
    if not user_id_str:
        raise _INVALID_CREDENTIALS

    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise _INVALID_CREDENTIALS from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.deleted_at is not None or not user.is_active:
        raise _INVALID_CREDENTIALS

    return user


def require_super_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Reject anyone who is not a super_admin."""
    if user.role is not UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin role required",
        )
    return user


def require_business_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Allow business admins and super admins through.

    Per docs/03-api.md, super admins can call business-admin endpoints with
    a ``?business_id=`` override. The role gate is permissive; the business
    scope is enforced separately by ``get_business_id_filter``.
    """
    if user.role not in {UserRole.BUSINESS_ADMIN, UserRole.SUPER_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Business admin role required",
        )
    return user


def get_business_id_filter(
    user: Annotated[User, Depends(get_current_user)],
) -> UUID | None:
    """Resolve the ``business_id`` value to filter queries by.

    For ``business_admin`` users this is their own ``business_id`` (guaranteed
    non-null by the ``ck_users_role_business_id`` check constraint). For
    ``super_admin`` users this is ``None`` — meaning "do not filter; see
    everything across the platform."

    Routers should use this in WHERE clauses on business-scoped tables:

        if business_id_filter is not None:
            query = query.where(SomeModel.business_id == business_id_filter)
    """
    if user.role is UserRole.SUPER_ADMIN:
        return None
    return user.business_id
