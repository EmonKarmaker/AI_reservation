"""Business model — one row per tenant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CHAR, Index, Integer, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import BusinessStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.business_setting import BusinessSetting
    from app.models.conversation import Conversation
    from app.models.customer import Customer
    from app.models.embedding import Embedding
    from app.models.escalation import Escalation
    from app.models.faq import Faq
    from app.models.operating_hours import OperatingHours
    from app.models.payment import Payment
    from app.models.schedule_exception import ScheduleException
    from app.models.service import Service
    from app.models.user import User


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

    settings: Mapped["BusinessSetting | None"] = relationship(
        back_populates="business", cascade="all, delete-orphan", uselist=False
    )
    users: Mapped[list["User"]] = relationship(back_populates="business")
    services: Mapped[list["Service"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    customers: Mapped[list["Customer"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["Escalation"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    faqs: Mapped[list["Faq"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list["Embedding"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    operating_hours: Mapped[list["OperatingHours"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    schedule_exceptions: Mapped[list["ScheduleException"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_businesses_status", "status"),
        Index("ix_businesses_deleted_at", "deleted_at"),
    )
