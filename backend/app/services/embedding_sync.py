"""Embedding synchronization for services and FAQs.

For each Service or FAQ create/update, we compose a short text representation,
generate a 384-dim MiniLM embedding, and upsert it into the ``embeddings``
table keyed by (source_type, source_id). On delete we drop the row.

Design notes:

- **Best-effort.** All public functions catch exceptions internally and log
  them; the caller's CRUD operation always succeeds. A stale embedding is
  much better than a save that fails because the model is unavailable.

- **Upsert via SELECT-then-INSERT/UPDATE.** Postgres has ``ON CONFLICT DO
  UPDATE`` for clean upserts, but using SQLAlchemy core with pgvector +
  asyncpg makes the syntax noisy. A read-then-write is fine here because
  CRUD is single-writer per (business, source_id) — race conditions aren't
  meaningful (and last-write-wins is the right semantic anyway).

- **Embedding generation is sync.** The MiniLM model is CPU-bound. We do not
  ``await`` it because there's nothing to await; it just runs in the request
  thread. Adds ~50-100 ms to the request; first-ever call after process
  start adds ~5 s for model load.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embeddings import embed_text
from app.models.embedding import Embedding
from app.models.enums import EmbeddingSourceType
from app.models.faq import Faq
from app.models.service import Service


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content composition — kept here so all embedding logic lives in one place
# ---------------------------------------------------------------------------

def _service_content(service: Service) -> str:
    """Compose a service into the text we embed.

    The form is "{name}. {description}" if a description exists, else just
    the name. Trailing period on the name when description is present helps
    the embedder treat them as separate sentences.
    """
    if service.description:
        return f"{service.name}. {service.description}"
    return service.name


def _faq_content(faq: Faq) -> str:
    """Compose a FAQ as "{question} {answer}".

    Single space separator; questions usually end with '?' and answers can
    start cleanly after.
    """
    return f"{faq.question} {faq.answer}"


# ---------------------------------------------------------------------------
# Core upsert (private)
# ---------------------------------------------------------------------------

async def _upsert_embedding(
    db: AsyncSession,
    *,
    business_id: UUID,
    source_type: EmbeddingSourceType,
    source_id: UUID,
    content: str,
) -> None:
    """Insert or update the embedding row for a (source_type, source_id) pair.

    Commits within this function — the caller's main CRUD commit has already
    happened. Wrapped in try/except by the public sync_* wrappers below.
    """
    vector = embed_text(content)

    result = await db.execute(
        select(Embedding).where(
            Embedding.source_type == source_type,
            Embedding.source_id == source_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        db.add(
            Embedding(
                business_id=business_id,
                source_type=source_type,
                source_id=source_id,
                content=content,
                embedding=vector,
            )
        )
    else:
        existing.content = content
        existing.embedding = vector
        # business_id intentionally not updated — an embedding cannot move
        # tenants. If business_id is wrong here, that's a real bug elsewhere.

    await db.commit()


async def _delete_embedding(
    db: AsyncSession,
    *,
    source_type: EmbeddingSourceType,
    source_id: UUID,
) -> None:
    """Delete the embedding row for a (source_type, source_id) pair, if any."""
    result = await db.execute(
        select(Embedding).where(
            Embedding.source_type == source_type,
            Embedding.source_id == source_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()


# ---------------------------------------------------------------------------
# Public API — best-effort wrappers used by routers
# ---------------------------------------------------------------------------

async def sync_service_embedding(db: AsyncSession, service: Service) -> None:
    """Upsert the embedding for a Service. Best-effort — never raises."""
    try:
        await _upsert_embedding(
            db,
            business_id=service.business_id,
            source_type=EmbeddingSourceType.SERVICE,
            source_id=service.id,
            content=_service_content(service),
        )
    except Exception as exc:  # noqa: BLE001 — intentionally broad
        logger.warning(
            "Failed to sync embedding for service %s: %s", service.id, exc
        )


async def sync_faq_embedding(db: AsyncSession, faq: Faq) -> None:
    """Upsert the embedding for a FAQ. Best-effort — never raises."""
    try:
        await _upsert_embedding(
            db,
            business_id=faq.business_id,
            source_type=EmbeddingSourceType.FAQ,
            source_id=faq.id,
            content=_faq_content(faq),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to sync embedding for faq %s: %s", faq.id, exc)


async def delete_service_embedding(db: AsyncSession, service_id: UUID) -> None:
    """Drop the embedding row for a service. Best-effort — never raises."""
    try:
        await _delete_embedding(
            db,
            source_type=EmbeddingSourceType.SERVICE,
            source_id=service_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to delete embedding for service %s: %s", service_id, exc
        )


async def delete_faq_embedding(db: AsyncSession, faq_id: UUID) -> None:
    """Drop the embedding row for a FAQ. Best-effort — never raises."""
    try:
        await _delete_embedding(
            db,
            source_type=EmbeddingSourceType.FAQ,
            source_id=faq_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete embedding for faq %s: %s", faq_id, exc)
