"""Admin services CRUD endpoints.

Business-scoped via ``get_business_id_filter`` (same multi-tenancy rule as
business.py). Soft-delete only — bookings may reference a service, so we set
``deleted_at`` rather than removing the row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import get_business_id_filter, require_business_admin
from app.models.service import Service
from app.models.user import User
from app.schemas.business import ServiceCreate, ServiceOut, ServiceUpdate
from app.services.embedding_sync import (
    delete_service_embedding,
    sync_service_embedding,
)


router = APIRouter(prefix="/admin/services", tags=["admin:services"])


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


async def _get_owned_service(
    db: AsyncSession,
    service_id: UUID,
    business_id: UUID,
) -> Service:
    """Fetch a non-deleted service that belongs to the given business.

    Returns 404 if the service does not exist OR belongs to a different
    business. We do NOT distinguish — a business admin must not be able to
    probe whether a service ID exists under another tenant.
    """
    result = await db.execute(
        select(Service).where(
            Service.id == service_id,
            Service.business_id == business_id,
            Service.deleted_at.is_(None),
        )
    )
    service = result.scalar_one_or_none()
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


@router.get("", response_model=list[ServiceOut])
async def list_services(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> list[Service]:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(Service)
        .where(Service.business_id == target, Service.deleted_at.is_(None))
        .order_by(Service.display_order, Service.name)
    )
    return list(result.scalars().all())


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
async def create_service(
    body: ServiceCreate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Service:
    target = await _resolve_business_id(business_id_filter, business_id)
    service = Service(business_id=target, **body.model_dump())
    db.add(service)
    await db.commit()
    await db.refresh(service)
    await sync_service_embedding(db, service)
    return service


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(
    service_id: UUID,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Service:
    target = await _resolve_business_id(business_id_filter, business_id)
    return await _get_owned_service(db, service_id, target)


@router.patch("/{service_id}", response_model=ServiceOut)
async def update_service(
    service_id: UUID,
    body: ServiceUpdate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Service:
    target = await _resolve_business_id(business_id_filter, business_id)
    service = await _get_owned_service(db, service_id, target)

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service)
    await sync_service_embedding(db, service)
    return service


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> None:
    target = await _resolve_business_id(business_id_filter, business_id)
    service = await _get_owned_service(db, service_id, target)
    service.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await delete_service_embedding(db, service.id)
    return None
