"""Auth request and response schemas.

Per docs/03-api.md section 1. These models define the wire contract between
frontend and backend for the five auth endpoints.

Naming convention:
- ``XRequest`` for inbound bodies
- ``XResponse`` for outbound bodies
- ``UserOut`` for user info embedded in responses (reused, not request-shaped)
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


# ---------------------------------------------------------------------------
# Reusable user shape (embedded in multiple responses)
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    """User info returned on login, refresh, and /auth/me."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    business_id: UUID | None = Field(
        default=None,
        description="Null for super_admin; required for business_admin",
    )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    """Create a business + first business admin in one call.

    Per docs/03-api.md, public in v1 for demo purposes; this endpoint will be
    restricted later (super-admin-only invite flow).
    """

    business_name: str = Field(..., min_length=1, max_length=200)
    business_slug: str = Field(
        ...,
        min_length=2,
        max_length=80,
        pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
        description="URL-safe identifier; lowercase, digits, and hyphens only",
    )
    industry: str | None = Field(default=None, max_length=80)
    timezone: str = Field(
        default="UTC",
        max_length=64,
        description="IANA timezone name, e.g. 'Asia/Dhaka'",
    )
    admin_email: EmailStr
    admin_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plaintext on the wire (over HTTPS); hashed before storage",
    )
    admin_full_name: str = Field(..., min_length=1, max_length=200)


class RegisterResponse(BaseModel):
    business_id: UUID
    user_id: UUID
    message: str = "Business created successfully"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    """Returned after successful login or refresh.

    JWT lives in the httpOnly cookie set by the response, NOT in this body.
    Frontend reads user info from this body and authenticates subsequent
    requests via the cookie automatically.
    """

    user: UserOut


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------

class MeResponse(BaseModel):
    user: UserOut
