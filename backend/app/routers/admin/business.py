"""Admin business-profile and settings endpoints.

All endpoints are business-scoped via ``get_business_id_filter``:
- business_admin: operates on their own business (filter = their business_id)
- super_admin: must pass ``?business_id=`` to target a specific business
  (filter = None means "no implicit business", so super_admin without the
  query param gets a 400)

This is the multi-tenancy boundary. Every query MUST be scoped by business_id.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import get_business_id_filter, require_business_admin
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.user import User
from app.schemas.business import (
    BusinessOut,
    BusinessSettingsOut,
    BusinessSettingsUpdate,
    BusinessUpdate,
)


router = APIRouter(prefix="/admin/business", tags=["admin:business"])


async def _resolve_business_id(
    business_id_filter: UUID | None,
    business_id_query: UUID | None,
) -> UUID:
    """Resolve which business this request targets.

    - business_admin: filter is their business_id; query param ignored.
    - super_admin: filter is None; they MUST supply ?business_id=.
    """
    if business_id_filter is not None:
        return business_id_filter
    if business_id_query is not None:
        return business_id_query
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="super_admin must supply ?business_id=",
    )


@router.get("", response_model=BusinessOut)
async def get_business(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Business:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(Business).where(
            Business.id == target,
            Business.deleted_at.is_(None),
        )
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


@router.patch("", response_model=BusinessOut)
async def update_business(
    body: BusinessUpdate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> Business:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(Business).where(
            Business.id == target,
            Business.deleted_at.is_(None),
        )
    )
    business = result.scalar_one_or_none()
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(business, field, value)

    await db.commit()
    await db.refresh(business)
    return business


@router.get("/settings", response_model=BusinessSettingsOut)
async def get_business_settings(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> BusinessSetting:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(BusinessSetting).where(BusinessSetting.business_id == target)
    )
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")
    return settings_row


@router.patch("/settings", response_model=BusinessSettingsOut)
async def update_business_settings(
    body: BusinessSettingsUpdate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> BusinessSetting:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(BusinessSetting).where(BusinessSetting.business_id == target)
    )
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settings not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(settings_row, field, value)

    await db.commit()
    await db.refresh(settings_row)
    return settings_row
