"""Embedding model — polymorphic vector store across business/service/faq.

Postgres column is named ``metadata``, Python attribute is ``extra_data``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin, pg_enum
from app.models.enums import EmbeddingSourceType

if TYPE_CHECKING:
    from app.models.business import Business


class Embedding(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "embeddings"

    business_id: Mapped[UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type: Mapped[EmbeddingSourceType] = mapped_column(
        pg_enum(EmbeddingSourceType, "embedding_source_type"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    business: Mapped["Business"] = relationship(back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_embeddings_source"),
        Index("ix_embeddings_business_id", "business_id"),
        Index(
            "ix_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
