"""OperatingHours — weekly recurring schedule, one row per (business, day)."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import DayOfWeek

if TYPE_CHECKING:
    from app.models.business import Business


class OperatingHours(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "operating_hours"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(
        pg_enum(DayOfWeek, "day_of_week"),
        nullable=False,
    )
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    business: Mapped["Business"] = relationship(back_populates="operating_hours")

    __table_args__ = (
        UniqueConstraint("business_id", "day_of_week", name="uq_operating_hours_business_day"),
        CheckConstraint(
            "is_closed OR close_time > open_time",
            name="ck_operating_hours_close_after_open",
        ),
    )
