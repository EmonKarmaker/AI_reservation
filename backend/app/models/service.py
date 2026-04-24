"""Service model — bookable services per business."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.business import Business


class Service(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "services"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    business: Mapped["Business"] = relationship(back_populates="services")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="service")

    __table_args__ = (
        CheckConstraint(
            "duration_minutes > 0 AND buffer_minutes >= 0 AND price >= 0",
            name="ck_services_positive_values",
        ),
        Index("ix_services_business_id", "business_id"),
        Index("ix_services_business_id_is_active", "business_id", "is_active"),
        Index("ix_services_deleted_at", "deleted_at"),
    )
