"""Deterministic slot finder for the booking flow.

Given a service, a target date, and (optionally) a time-of-day preference,
returns up to N available start times on that date.

Algorithm:
1. Look up the business's operating_hours for the date's weekday.
2. Generate a 30-minute grid of candidate start times from open_time to
   (close_time - service.duration_minutes).
3. Look up existing bookings for that date in active statuses
   (PENDING_PAYMENT, CONFIRMED).
4. Drop candidate slots that overlap any existing booking (taking
   service.buffer_minutes into account).
5. Filter by time_window if specified ("morning" / "afternoon" / "evening").
6. Return the first `limit` survivors.

All times in this module are NAIVE LOCAL times in the business's timezone.
Conversion to UTC happens at the booking-creation boundary (Phase 4.6.4),
not here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.business import Business
from app.models.enums import BookingStatus
from app.models.operating_hours import OperatingHours
from app.models.service import Service


logger = logging.getLogger(__name__)


SLOT_GRANULARITY_MINUTES = 30

# Map Python date.weekday() (Mon=0..Sun=6) to the 3-letter strings used in
# operating_hours.day_of_week.
_WEEKDAY_TO_DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Time-of-day windows in local time. Used to filter slots when the customer
# says "morning" / "afternoon" / "evening".
_TIME_WINDOWS: dict[str, tuple[time, time]] = {
    "morning": (time(0, 0), time(12, 0)),
    "afternoon": (time(12, 0), time(17, 0)),
    "evening": (time(17, 0), time(23, 59, 59)),
}

# Bookings in these statuses block a slot. CANCELLED/COMPLETED/NO_SHOW don't.
_BLOCKING_STATUSES = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)


@dataclass(slots=True)
class Slot:
    """An available booking start time, in business-local naive datetime."""

    start_local: datetime  # naive local datetime
    end_local: datetime  # naive local datetime (start + service duration)

    @property
    def display(self) -> str:
        """Human-friendly formatted time, e.g. '10:30 AM'."""
        return self.start_local.strftime("%I:%M %p").lstrip("0")

    @property
    def iso(self) -> str:
        """ISO datetime string for storing in JSON state."""
        return self.start_local.isoformat()


def weekday_string(d: date) -> str:
    """Convert a date to the 3-letter weekday key used in operating_hours."""
    return _WEEKDAY_TO_DOW[d.weekday()]


def extract_time_window(message: str) -> str | None:
    """Cheap substring search for 'morning' / 'afternoon' / 'evening'.

    Deterministic and free — no LLM call. Returns None if nothing matches.
    """
    lower = message.lower()
    if "morning" in lower:
        return "morning"
    if "afternoon" in lower:
        return "afternoon"
    if "evening" in lower or "night" in lower:
        return "evening"
    return None


async def _get_operating_hours(
    db: AsyncSession, business_id: UUID, dow: str
) -> OperatingHours | None:
    result = await db.execute(
        select(OperatingHours).where(
            OperatingHours.business_id == business_id,
            OperatingHours.day_of_week == dow,
        )
    )
    return result.scalar_one_or_none()


async def _get_blocking_bookings_for_day(
    db: AsyncSession,
    business_id: UUID,
    target_date: date,
    tz: ZoneInfo,
) -> list[Booking]:
    """Bookings on `target_date` whose status blocks new slots."""
    # Day boundaries in business-local time, converted to UTC for the DB.
    # We use TZ-aware datetimes so the comparison is unambiguous regardless
    # of how the DB stores the column.
    day_start = datetime.combine(target_date, time(0, 0, 0), tzinfo=tz)
    day_end = datetime.combine(target_date, time(23, 59, 59), tzinfo=tz)

    result = await db.execute(
        select(Booking).where(
            Booking.business_id == business_id,
            Booking.status.in_(_BLOCKING_STATUSES),
            Booking.deleted_at.is_(None),
            Booking.starts_at >= day_start,
            Booking.starts_at <= day_end,
        )
    )
    return list(result.scalars().all())


def _overlaps(
    a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime
) -> bool:
    """Half-open interval overlap: [a_start, a_end) vs [b_start, b_end)."""
    return a_start < b_end and b_start < a_end


def _generate_grid(
    target_date: date,
    open_time: time,
    close_time: time,
    duration_minutes: int,
    granularity_minutes: int = SLOT_GRANULARITY_MINUTES,
) -> list[datetime]:
    """All candidate start times on `target_date`, naive local."""
    starts: list[datetime] = []
    cursor = datetime.combine(target_date, open_time)
    close_dt = datetime.combine(target_date, close_time)
    last_valid_start = close_dt - timedelta(minutes=duration_minutes)
    step = timedelta(minutes=granularity_minutes)

    while cursor <= last_valid_start:
        starts.append(cursor)
        cursor += step

    return starts


async def find_available_slots(
    db: AsyncSession,
    *,
    business: Business,
    service: Service,
    target_date: date,
    time_window: str | None = None,
    limit: int = 3,
) -> list[Slot]:
    """Return up to `limit` available slots for `service` on `target_date`.

    Returns [] if the business is closed that day, has no hours configured,
    or every candidate slot conflicts with an existing booking.
    """
    if limit <= 0:
        return []

    try:
        tz = ZoneInfo(business.timezone)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Unknown business timezone %r; using UTC for booking lookups",
            business.timezone,
        )
        tz = ZoneInfo("UTC")

    dow = weekday_string(target_date)
    hours = await _get_operating_hours(db, business.id, dow)
    if hours is None or hours.is_closed:
        logger.info(
            "find_available_slots: business=%s closed on %s (%s)",
            business.id,
            target_date,
            dow,
        )
        return []

    # Block size for conflict purposes = service duration + buffer
    block_minutes = service.duration_minutes + (service.buffer_minutes or 0)

    grid = _generate_grid(
        target_date=target_date,
        open_time=hours.open_time,
        close_time=hours.close_time,
        duration_minutes=block_minutes,
    )
    if not grid:
        logger.info(
            "find_available_slots: no grid slots — open=%s close=%s block=%dm",
            hours.open_time,
            hours.close_time,
            block_minutes,
        )
        return []

    # Existing bookings on this date. We compare against the booking's actual
    # [starts_at, ends_at] interval, not block_minutes — the buffer applies to
    # the *new* slot, not the stored row.
    bookings = await _get_blocking_bookings_for_day(
        db, business.id, target_date, tz
    )

    # Convert bookings to naive local datetimes for comparison with the grid.
    busy_intervals: list[tuple[datetime, datetime]] = []
    for b in bookings:
        # If starts_at/ends_at are tz-aware (TIMESTAMPTZ), convert to local.
        # If naive, assume they're already in business-local time (no other
        # sensible interpretation given the schema).
        bs = b.starts_at
        be = b.ends_at
        if bs.tzinfo is not None:
            bs = bs.astimezone(tz).replace(tzinfo=None)
        if be.tzinfo is not None:
            be = be.astimezone(tz).replace(tzinfo=None)
        # Apply buffer to the END of existing booking too — the new slot must
        # not start during another booking's buffer-out window.
        be_padded = be + timedelta(minutes=service.buffer_minutes or 0)
        busy_intervals.append((bs, be_padded))

    # Now exclude (a) past slots if target_date is today, (b) conflicts.
    now_local = datetime.now(tz=tz).replace(tzinfo=None)

    survivors: list[Slot] = []
    for slot_start in grid:
        slot_end = slot_start + timedelta(minutes=block_minutes)

        if slot_start <= now_local:
            continue  # in the past or right now — not bookable

        conflict = any(
            _overlaps(slot_start, slot_end, bs, be) for bs, be in busy_intervals
        )
        if conflict:
            continue

        if time_window:
            window = _TIME_WINDOWS.get(time_window)
            if window is not None:
                w_start, w_end = window
                if not (w_start <= slot_start.time() < w_end):
                    continue

        survivors.append(
            Slot(
                start_local=slot_start,
                end_local=slot_start + timedelta(minutes=service.duration_minutes),
            )
        )
        if len(survivors) >= limit:
            break

    logger.info(
        "find_available_slots: business=%s service=%r date=%s window=%r → %d slots",
        business.id,
        service.name,
        target_date,
        time_window,
        len(survivors),
    )
    return survivors
