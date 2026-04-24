"""Customer model — end users who book."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.business import Business
    from app.models.conversation import Conversation


class Customer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="customers")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL",
            name="ck_customers_email_or_phone",
        ),
        Index("ix_customers_business_id", "business_id"),
        Index("ix_customers_business_id_phone", "business_id", "phone"),
        Index("ix_customers_business_id_email", "business_id", "email"),
    )
