"""Security primitives: JWT encoding/decoding and password hashing.

This module is HTTP-agnostic. It does not import from FastAPI or know about
requests, cookies, or routes — those concerns live in the auth routers
(Phase 1.7) and dependency wrappers (Phase 1.6).

Public surface:

- ``hash_password(plain)`` / ``verify_password(plain, hashed)`` — bcrypt via passlib
- ``create_access_token(subject, role, business_id)`` — short-lived (15m default)
- ``create_refresh_token(subject)`` — long-lived (7d default), no role/business
- ``decode_token(token, expected_type)`` — verifies sig + expiry + type claim
- ``TokenData`` — Pydantic model representing decoded access-token payload
- ``TokenError`` — raised on any decode failure (signature, expiry, type, malformed)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.config import settings
from app.models.enums import UserRole


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# bcrypt cost factor 12 → ~250ms per hash on modern hardware. Slow enough to
# resist brute force, fast enough for an interactive login.
#
# We use ``bcrypt`` directly rather than passlib. passlib 1.7.4 is incompatible
# with bcrypt 5.x (it reads a private attribute that no longer exists), and
# passlib has been effectively unmaintained since 2020.
#
# bcrypt has a hard 72-byte limit on the input password; longer values are
# truncated by some implementations, error in others. We pre-truncate to 72
# bytes of UTF-8 to make behavior deterministic across versions and to match
# what most production stacks do.
_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(plain: str) -> bytes:
    """Encode and truncate a password for bcrypt's 72-byte input limit."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    digest = bcrypt.hashpw(_to_bcrypt_bytes(plain), salt)
    return digest.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the previously-hashed value."""
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash string — treat as a non-match rather than crashing.
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

class TokenError(Exception):
    """Raised when a token fails signature verification, expiry, or type check."""


class TokenData(BaseModel):
    """Decoded access-token payload.

    Refresh tokens decode to a different shape (no role/business_id); callers
    should branch on ``type`` before constructing this model.
    """

    sub: str = Field(..., description="User ID (UUID as string)")
    role: UserRole = Field(..., description="User role at issue time")
    business_id: UUID | None = Field(
        default=None, description="Business scope; null for super_admin"
    )
    iat: int = Field(..., description="Issued-at (unix timestamp)")
    exp: int = Field(..., description="Expires-at (unix timestamp)")
    type: Literal["access"] = Field(..., description="Token kind")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def create_access_token(
    subject: str | UUID,
    role: UserRole,
    business_id: UUID | None,
) -> str:
    """Create a short-lived access token.

    The subject is the user's UUID. Role and business_id are embedded so
    request handlers can authorize without an extra DB lookup.
    """
    now = _utcnow()
    expires = now + timedelta(minutes=settings.JWT_ACCESS_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role.value,
        "business_id": str(business_id) if business_id is not None else None,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | UUID) -> str:
    """Create a long-lived refresh token.

    Refresh tokens carry only enough information to prove the session is still
    valid. Role and business_id are NOT embedded — the auth router fetches the
    current values from the DB when issuing a new access token.
    """
    now = _utcnow()
    expires = now + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(
    token: str,
    expected_type: Literal["access", "refresh"],
) -> dict[str, Any]:
    """Decode and verify a JWT.

    Verifies signature, expiry (built into ``jwt.decode``), and the ``type``
    claim. Raises ``TokenError`` on any failure. Returns the raw claims dict;
    callers can wrap in ``TokenData`` for access tokens.
    """
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    actual_type = claims.get("type")
    if actual_type != expected_type:
        raise TokenError(
            f"Wrong token type: expected '{expected_type}', got '{actual_type}'"
        )

    return claims
