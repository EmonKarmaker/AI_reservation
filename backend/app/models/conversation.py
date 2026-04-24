"""Conversation model — one row per chat session or voice call."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import ConversationChannel, ConversationStatus

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.business import Business
    from app.models.customer import Customer
    from app.models.escalation import Escalation
    from app.models.message import Message


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel: Mapped[ConversationChannel] = mapped_column(
        pg_enum(ConversationChannel, "conversation_channel"),
        nullable=False,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        pg_enum(ConversationStatus, "conversation_status"),
        nullable=False,
        server_default="active",
    )
    session_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    vapi_call_id: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    langgraph_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    intent_history: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped["Business"] = relationship(back_populates="conversations")
    customer: Mapped["Customer | None"] = relationship(back_populates="conversations")
    booking: Mapped["Booking | None"] = relationship(
        back_populates="conversation", foreign_keys="Booking.conversation_id"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["Escalation"]] = relationship(back_populates="conversation")

    __table_args__ = (
        Index("ix_conversations_business_id", "business_id"),
        Index(
            "ix_conversations_business_id_created_at",
            "business_id",
            text("created_at DESC"),
        ),
        Index("ix_conversations_status", "status"),
    )
