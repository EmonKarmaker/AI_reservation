"""User model — both super_admin and business_admin live here."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.escalation import Escalation


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"), nullable=False)
    business_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped["Business | None"] = relationship(back_populates="users")
    resolved_escalations: Mapped[list["Escalation"]] = relationship(
        back_populates="resolved_by_user",
        foreign_keys="Escalation.resolved_by",
    )

    __table_args__ = (
        CheckConstraint(
            "(role = 'super_admin' AND business_id IS NULL) "
            "OR (role = 'business_admin' AND business_id IS NOT NULL)",
            name="ck_users_role_business_id",
        ),
        Index("ix_users_business_id", "business_id"),
        Index("ix_users_role", "role"),
    )
