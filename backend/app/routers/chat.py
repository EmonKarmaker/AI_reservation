"""Public chat endpoint. POST /chat/{business_slug}.

This is the one customer-facing API in the product. Anonymous — no auth.
Returns AI-generated replies grounded in the business's services and FAQs.

Multi-tenancy: business_slug → Business row → business_id is the ONLY
tenant scope that flows down into chat_graph / RAG / persistence. There is
no cross-tenant data path through this endpoint.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.business import Business
from app.models.enums import BusinessStatus
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_graph import run_chat_turn


router = APIRouter(prefix="/chat", tags=["chat"])


async def _resolve_business(
    db: AsyncSession,
    slug: str,
) -> Business:
    """Find an active, non-deleted business by slug.

    Returns 404 for any of: slug unknown, business soft-deleted, business
    status != active. We don't distinguish — the customer should never be
    able to probe which slugs exist.
    """
    result = await db.execute(
        select(Business).where(
            Business.slug == slug,
            Business.deleted_at.is_(None),
            Business.status == BusinessStatus.ACTIVE,
        )
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found",
        )
    return business


@router.post(
    "/{business_slug}",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
)
async def chat(
    business_slug: str,
    body: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChatResponse:
    """Run one chat turn against ``business_slug`` and return the AI reply.

    If the client doesn't pass ``customer_id`` we mint one. Either way it's
    echoed in the response so the client can persist it (localStorage) and
    use it on subsequent turns. A stable customer_id keeps the same
    conversation row alive across turns.
    """
    business = await _resolve_business(db, business_slug)

    customer_id: UUID = body.customer_id or uuid4()

    state = await run_chat_turn(
        db=db,
        business_id=business.id,
        business_name=business.name,
        customer_id=customer_id,
        user_message=body.message,
        business_greeting=business.ai_greeting,
        business_personality=business.ai_personality,
    )

    if state.conversation_id is None:
        # Shouldn't happen: load_history_node always creates/fetches a
        # conversation. If it does, surface a 500 rather than returning a
        # malformed ChatResponse.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat turn did not produce a conversation_id",
        )

    return ChatResponse(
        conversation_id=state.conversation_id,
        customer_id=customer_id,
        message=state.assistant_message,
        intent=str(state.intent),
    )
