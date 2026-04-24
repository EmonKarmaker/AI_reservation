"""Payment model — Stripe payment records, one-to-many with Booking."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import PaymentStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.business import Business


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    booking_id: Mapped[UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"),
        nullable=False,
        server_default="pending",
    )
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        Text, unique=True, nullable=True
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    stripe_refund_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped["Business"] = relationship(back_populates="payments")
    booking: Mapped["Booking"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("ix_payments_business_id", "business_id"),
        Index("ix_payments_booking_id", "booking_id"),
        Index("ix_payments_status", "status"),
    )
