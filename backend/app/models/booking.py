"""Booking model — the central entity linking customer + service + conversation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import BookingStatus


class Booking(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "bookings"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Forward FK reference: the ``conversations`` table is defined in Phase 1.3c.
    # SQLAlchemy resolves string-based FKs at configure time, so declaring it now is safe.
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"),
        nullable=False,
        server_default="pending_payment",
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_bookings_ends_after_starts"),
        Index("ix_bookings_business_id", "business_id"),
        Index("ix_bookings_business_id_starts_at", "business_id", "starts_at"),
        Index("ix_bookings_customer_id", "customer_id"),
        Index("ix_bookings_service_id", "service_id"),
        Index("ix_bookings_status", "status"),
    )
