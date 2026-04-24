"""Business model — one row per tenant."""

from __future__ import annotations

from sqlalchemy import CHAR, Index, Integer, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import BusinessStatus


class Business(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "businesses"

    slug: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default="USD")
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BusinessStatus] = mapped_column(
        pg_enum(BusinessStatus, "business_status"),
        nullable=False,
        server_default="active",
    )
    ai_personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    cancellation_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    stripe_account_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_businesses_status", "status"),
        Index("ix_businesses_deleted_at", "deleted_at"),
    )
