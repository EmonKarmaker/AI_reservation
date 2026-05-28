"""Admin schemas for business profile, business settings, and services.

Per docs/03-api.md admin section. Update schemas use all-optional fields so
PATCH semantics work (only provided fields are changed).
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BusinessStatus


# ---------------------------------------------------------------------------
# Business profile
# ---------------------------------------------------------------------------

class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str | None
    industry: str | None
    timezone: str
    currency: str
    phone: str | None
    email: str | None
    website: str | None
    address: str | None
    logo_url: str | None
    status: BusinessStatus
    ai_personality: str | None
    ai_greeting: str | None
    booking_window_days: int
    cancellation_hours: int


class BusinessUpdate(BaseModel):
    """PATCH body for business profile. All optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    industry: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    ai_personality: str | None = Field(default=None, max_length=2000)
    ai_greeting: str | None = Field(default=None, max_length=2000)
    booking_window_days: int | None = Field(default=None, ge=1, le=365)
    cancellation_hours: int | None = Field(default=None, ge=0, le=720)


# ---------------------------------------------------------------------------
# Business settings
# ---------------------------------------------------------------------------

class BusinessSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    require_payment_at_booking: bool
    deposit_percentage: int
    auto_confirm_bookings: bool
    send_reminder_hours_before: int
    escalation_email: str | None
    max_daily_bookings: int | None


class BusinessSettingsUpdate(BaseModel):
    """PATCH body for business settings. All optional.

    NOTE: custom_api_key_encrypted is intentionally NOT exposed here — API key
    management is a separate, encrypted flow (Phase 10). Never accept or return
    the raw key through this schema.
    """

    require_payment_at_booking: bool | None = None
    deposit_percentage: int | None = Field(default=None, ge=0, le=100)
    auto_confirm_bookings: bool | None = None
    send_reminder_hours_before: int | None = Field(default=None, ge=0, le=168)
    escalation_email: str | None = Field(default=None, max_length=255)
    max_daily_bookings: int | None = Field(default=None, ge=1, le=1000)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    name: str
    description: str | None
    duration_minutes: int
    buffer_minutes: int
    price: Decimal
    is_active: bool
    display_order: int
    image_url: str | None


class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int = Field(..., ge=1, le=1440)
    buffer_minutes: int = Field(default=0, ge=0, le=480)
    price: Decimal = Field(..., ge=0)
    is_active: bool = Field(default=True)
    display_order: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)


class ServiceUpdate(BaseModel):
    """PATCH body. All optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    buffer_minutes: int | None = Field(default=None, ge=0, le=480)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
