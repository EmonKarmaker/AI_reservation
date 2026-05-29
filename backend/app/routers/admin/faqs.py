"""Admin FAQ CRUD endpoints.

Business-scoped. Hard-delete (nothing references FAQs, unlike services).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import get_business_id_filter, require_business_admin
from app.models.faq import Faq
from app.models.user import User
from app.schemas.hours_faqs import FaqCreate, FaqOut, FaqUpdate
from app.services.embedding_sync import delete_faq_embedding, sync_faq_embedding


router = APIRouter(prefix="/admin/faqs", tags=["admin:faqs"])


async def _resolve_business_id(
    business_id_filter: UUID | None,
    business_id_query: UUID | None,
) -> UUID:
    if business_id_filter is not None:
        return business_id_filter
    if business_id_query is not None:
        return business_id_query
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="super_admin must supply ?business_id=",
    )


async def _get_owned_faq(db: AsyncSession, faq_id: UUID, business_id: UUID) -> Faq:
    result = await db.execute(
        select(Faq).where(Faq.id == faq_id, Faq.business_id == business_id)
    )
    faq = result.scalar_one_or_none()
    if faq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ not found")
    return faq


@router.get("", response_model=list[FaqOut])
async def list_faqs(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> list[Faq]:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(Faq)
        .where(Faq.business_id == target)
        .order_by(Faq.display_order, Faq.question)
    )
    return list(result.scalars().all())


@router.post("", response_model=FaqOut, status_code=status.HTTP_201_CREATED)
async def create_faq(
    body: FaqCreate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Faq:
    target = await _resolve_business_id(business_id_filter, business_id)
    faq = Faq(business_id=target, **body.model_dump())
    db.add(faq)
    await db.commit()
    await db.refresh(faq)
    await sync_faq_embedding(db, faq)
    return faq


@router.get("/{faq_id}", response_model=FaqOut)
async def get_faq(
    faq_id: UUID,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Faq:
    target = await _resolve_business_id(business_id_filter, business_id)
    return await _get_owned_faq(db, faq_id, target)


@router.patch("/{faq_id}", response_model=FaqOut)
async def update_faq(
    faq_id: UUID,
    body: FaqUpdate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Faq:
    target = await _resolve_business_id(business_id_filter, business_id)
    faq = await _get_owned_faq(db, faq_id, target)
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(faq, field, value)
    await db.commit()
    await db.refresh(faq)
    await sync_faq_embedding(db, faq)
    return faq


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: UUID,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> None:
    target = await _resolve_business_id(business_id_filter, business_id)
    faq = await _get_owned_faq(db, faq_id, target)
    faq_id_for_embedding = faq.id
    await db.delete(faq)
    await db.commit()
    await delete_faq_embedding(db, faq_id_for_embedding)
    return None
