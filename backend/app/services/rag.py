"""Retrieval-augmented generation helper.

Given a free-form user query and a business_id, returns the top-k most
similar service/FAQ embeddings for that business. Used by the chatbot to
ground LLM responses on actual business data rather than making things up.

Multi-tenancy is enforced HERE: every query is filtered by ``business_id``.
A business_admin cannot accidentally retrieve another tenant's data via this
function; there is no path that lets you skip the business_id filter.

Distance metric: **cosine** (matches the HNSW index built in Phase 1.4 with
``vector_cosine_ops``). Lower distance = more similar. Distance is in
[0, 2] where 0 means identical direction.

Top-k default: 5. Plenty for a chatbot to ground on without bloating the LLM
context; tuneable per call when needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embeddings import embed_text
from app.models.embedding import Embedding
from app.models.enums import EmbeddingSourceType


DEFAULT_TOP_K = 5


@dataclass(slots=True)
class RetrievedChunk:
    """One result from a RAG retrieval.

    Carries enough info for the chatbot to (a) ground its answer on
    ``content``, and (b) optionally link back to the source row via
    ``source_type`` + ``source_id`` for analytics / escalation.
    """

    source_type: EmbeddingSourceType
    source_id: UUID
    content: str
    distance: float  # cosine distance, lower = more relevant


async def retrieve_relevant(
    db: AsyncSession,
    *,
    business_id: UUID,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source_types: list[EmbeddingSourceType] | None = None,
) -> list[RetrievedChunk]:
    """Return the top-k embeddings most similar to ``query`` for ``business_id``.

    Args:
        db: Active async session.
        business_id: REQUIRED. The tenant whose embeddings to search. Never
                     pass None here; if a caller doesn't know the business
                     id, they shouldn't be calling RAG.
        query: Free-form user question or statement. Embedded via MiniLM.
        top_k: Max results to return. Defaults to 5.
        source_types: Optional filter, e.g. [SERVICE] to only retrieve
                      services. None means all source types for this
                      business.

    Returns:
        A list of RetrievedChunk, ordered by ascending distance (most
        relevant first). May be empty if the business has no embeddings yet,
        or if top_k=0.
    """
    if top_k <= 0:
        return []

    query_vector = embed_text(query)

    # pgvector exposes cosine_distance on the Vector column type. Aliased to
    # 'distance' so we can both order by it and read it back in the result.
    distance = Embedding.embedding.cosine_distance(query_vector).label("distance")

    stmt = (
        select(
            Embedding.source_type,
            Embedding.source_id,
            Embedding.content,
            distance,
        )
        .where(Embedding.business_id == business_id)
        .order_by(distance)
        .limit(top_k)
    )

    if source_types:
        stmt = stmt.where(Embedding.source_type.in_(source_types))

    result = await db.execute(stmt)
    return [
        RetrievedChunk(
            source_type=row.source_type,
            source_id=row.source_id,
            content=row.content,
            distance=float(row.distance),
        )
        for row in result
    ]
