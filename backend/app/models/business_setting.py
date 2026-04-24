"""BusinessSetting — per-tenant configuration, 1:1 with Business."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class BusinessSetting(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "business_settings"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    require_payment_at_booking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deposit_percentage: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    auto_confirm_bookings: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    send_reminder_hours_before: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="24"
    )
    escalation_email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    max_daily_bookings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
