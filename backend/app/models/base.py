"""SQLAlchemy Base class and reusable mixins.

- ``Base``: the declarative base every model inherits from.
- ``UUIDMixin``: UUID primary key with Postgres-side ``gen_random_uuid()`` default
  (requires the ``pgcrypto`` extension, already installed by migration
  ``8c5d604ee81d_extensions_and_enums``).
- ``TimestampMixin``: ``created_at`` + ``updated_at`` ``timestamptz`` columns, UTC,
  auto-managed by the database.
- ``SoftDeleteMixin``: nullable ``deleted_at`` for tables that support soft delete.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UUIDMixin:
    """Adds a UUID primary key with a Postgres-side default."""

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )


class TimestampMixin:
    """Adds ``created_at`` and ``updated_at`` timestamps, managed by Postgres."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds a nullable ``deleted_at`` timestamp for soft-deletable tables."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
