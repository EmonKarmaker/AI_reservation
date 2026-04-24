"""Escalation model — triggered when AI hands off to a human."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import EscalationPriority, EscalationStatus

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.conversation import Conversation
    from app.models.user import User


class Escalation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "escalations"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_email: Mapped[str | None] = mapped_column(CITEXT(), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[EscalationPriority] = mapped_column(
        pg_enum(EscalationPriority, "escalation_priority"),
        nullable=False,
        server_default="medium",
    )
    status: Mapped[EscalationStatus] = mapped_column(
        pg_enum(EscalationStatus, "escalation_status"),
        nullable=False,
        server_default="open",
    )
    transcript_snapshot: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    suggested_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped["Business"] = relationship(back_populates="escalations")
    conversation: Mapped["Conversation"] = relationship(back_populates="escalations")
    resolved_by_user: Mapped["User | None"] = relationship(
        back_populates="resolved_escalations", foreign_keys=[resolved_by]
    )

    __table_args__ = (
        Index("ix_escalations_business_id", "business_id"),
        Index("ix_escalations_business_id_status", "business_id", "status"),
        Index(
            "ix_escalations_priority_created_at",
            "priority",
            text("created_at DESC"),
        ),
        Index("ix_escalations_conversation_id", "conversation_id"),
    )
