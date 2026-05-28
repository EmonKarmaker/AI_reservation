"""Admin operating-hours and schedule-exception endpoints.

Hours use PUT-the-whole-grid semantics: the weekly schedule is a fixed
structure, so replacing all submitted days at once is cleaner than per-row
PATCH. The handler upserts each submitted day.

All endpoints business-scoped via get_business_id_filter.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import get_business_id_filter, require_business_admin
from app.models.operating_hours import OperatingHours
from app.models.schedule_exception import ScheduleException
from app.models.user import User
from app.schemas.hours_faqs import (
    OperatingHoursOut,
    OperatingHoursReplace,
    ScheduleExceptionCreate,
    ScheduleExceptionOut,
)


router = APIRouter(prefix="/admin/hours", tags=["admin:hours"])


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


@router.get("", response_model=OperatingHoursOut)
async def get_hours(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> OperatingHoursOut:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(OperatingHours)
        .where(OperatingHours.business_id == target)
        .order_by(OperatingHours.day_of_week)
    )
    rows = list(result.scalars().all())
    return OperatingHoursOut(days=rows)  # type: ignore[arg-type]


@router.put("", response_model=OperatingHoursOut)
async def replace_hours(
    body: OperatingHoursReplace,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> OperatingHoursOut:
    target = await _resolve_business_id(business_id_filter, business_id)

    # Reject duplicate days in the payload.
    seen = [d.day_of_week for d in body.days]
    if len(seen) != len(set(seen)):
        raise HTTPException(
            status_code=422,
            detail="Each day_of_week may appear at most once",
        )

    existing_result = await db.execute(
        select(OperatingHours).where(OperatingHours.business_id == target)
    )
    existing = {row.day_of_week: row for row in existing_result.scalars().all()}

    from datetime import time as _time

    _MIDNIGHT = _time(0, 0)

    for day in body.days:
        # open_time/close_time are NOT NULL in the DB. For closed days, or when
        # a caller omits a time, default to 00:00:00 — is_closed is the real
        # source of truth for whether the business operates that day.
        open_t = day.open_time if day.open_time is not None else _MIDNIGHT
        close_t = day.close_time if day.close_time is not None else _MIDNIGHT

        row = existing.get(day.day_of_week)
        if row is None:
            db.add(OperatingHours(
                business_id=target,
                day_of_week=day.day_of_week,
                open_time=open_t,
                close_time=close_t,
                is_closed=day.is_closed,
            ))
        else:
            row.open_time = open_t
            row.close_time = close_t
            row.is_closed = day.is_closed

    await db.commit()

    refreshed = await db.execute(
        select(OperatingHours)
        .where(OperatingHours.business_id == target)
        .order_by(OperatingHours.day_of_week)
    )
    return OperatingHoursOut(days=list(refreshed.scalars().all()))  # type: ignore[arg-type]


@router.get("/exceptions", response_model=list[ScheduleExceptionOut])
async def list_exceptions(
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
    upcoming_only: bool = Query(default=True),
) -> list[ScheduleException]:
    target = await _resolve_business_id(business_id_filter, business_id)
    query = select(ScheduleException).where(ScheduleException.business_id == target)
    if upcoming_only:
        query = query.where(ScheduleException.exception_date >= date_type.today())
    query = query.order_by(ScheduleException.exception_date)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/exceptions",
    response_model=ScheduleExceptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_exception(
    body: ScheduleExceptionCreate,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> ScheduleException:
    target = await _resolve_business_id(business_id_filter, business_id)
    exc = ScheduleException(business_id=target, **body.model_dump())
    db.add(exc)
    await db.commit()
    await db.refresh(exc)
    return exc


@router.delete(
    "/exceptions/{exception_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_exception(
    exception_id: UUID,
    _user: Annotated[User, Depends(require_business_admin)],
    business_id_filter: Annotated[UUID | None, Depends(get_business_id_filter)],
    db: Annotated[AsyncSession, Depends(get_db)],
    business_id: UUID | None = Query(default=None),
) -> None:
    target = await _resolve_business_id(business_id_filter, business_id)
    result = await db.execute(
        select(ScheduleException).where(
            ScheduleException.id == exception_id,
            ScheduleException.business_id == target,
        )
    )
    exc = result.scalar_one_or_none()
    if exc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found")
    await db.delete(exc)
    await db.commit()
    return None
