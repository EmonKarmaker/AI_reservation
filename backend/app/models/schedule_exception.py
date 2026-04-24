"""ScheduleException — one-off closures or special hours (holidays, sick days)."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleException(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "schedule_exceptions"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    exception_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "exception_date",
            name="uq_schedule_exceptions_business_date",
        ),
    )
