"""Deterministic slot finder for the booking flow.

Given a service, a target date, and (optionally) a time-of-day preference,
returns up to N available start times on that date.

Algorithm:
1. Resolve the day's hours: a schedule_exceptions row for that exact date
   (holiday closure or special hours) wins over the weekly
   operating_hours row for the weekday.
2. If business_settings.max_daily_bookings is set and the day already has
   that many active bookings, the day is full.
3. Generate a 30-minute grid of candidate start times from open_time to
   (close_time - service.duration_minutes - buffer).
4. Look up existing bookings for that date in active statuses
   (PENDING_PAYMENT, CONFIRMED).
5. Drop candidate slots that overlap any existing booking (taking
   service.buffer_minutes into account) or that are already in the past.
6. Filter by time_window if specified ("morning" / "afternoon" / "evening").
7. Return the first `limit` survivors.

The pure part (steps 3, 5, 6, 7) lives in ``compute_slots`` so it can be
unit-tested without a database. ``is_slot_still_available`` re-runs the
same checks for one chosen start time just before a booking is written,
so a slot taken by another customer in the meantime is caught.

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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.enums import BookingStatus
from app.models.operating_hours import OperatingHours
from app.models.schedule_exception import ScheduleException
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


@dataclass(slots=True)
class DayHours:
    """Resolved opening hours for one calendar date.

    ``is_open`` False means no bookings that day. ``reason`` carries the
    schedule-exception reason (e.g. "Eid holiday") when there is one, so the
    chatbot can explain the closure.
    """

    is_open: bool
    open_time: time | None = None
    close_time: time | None = None
    reason: str | None = None


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


async def _get_schedule_exception(
    db: AsyncSession, business_id: UUID, target_date: date
) -> ScheduleException | None:
    result = await db.execute(
        select(ScheduleException).where(
            ScheduleException.business_id == business_id,
            ScheduleException.exception_date == target_date,
        )
    )
    return result.scalar_one_or_none()


def resolve_hours(
    weekly: OperatingHours | None,
    exception: ScheduleException | None,
) -> DayHours:
    """Combine the weekly schedule with a one-off exception for one date.

    Pure function. Rules:
    - An exception row for the date always wins.
      - ``is_closed`` (or missing / inverted times) -> closed that day.
      - otherwise -> open with the exception's special hours.
    - No exception: fall back to the weekly row; missing or ``is_closed``
      means closed.
    """
    if exception is not None:
        reason = (exception.reason or "").strip() or None
        if (
            exception.is_closed
            or exception.open_time is None
            or exception.close_time is None
            or exception.close_time <= exception.open_time
        ):
            return DayHours(is_open=False, reason=reason)
        return DayHours(
            is_open=True,
            open_time=exception.open_time,
            close_time=exception.close_time,
            reason=reason,
        )

    if weekly is None or weekly.is_closed:
        return DayHours(is_open=False)
    return DayHours(is_open=True, open_time=weekly.open_time, close_time=weekly.close_time)


async def get_day_hours(
    db: AsyncSession, business_id: UUID, target_date: date
) -> DayHours:
    """Opening hours for ``target_date``, honoring schedule exceptions."""
    weekly = await _get_operating_hours(db, business_id, weekday_string(target_date))
    exception = await _get_schedule_exception(db, business_id, target_date)
    return resolve_hours(weekly, exception)


async def _get_max_daily_bookings(db: AsyncSession, business_id: UUID) -> int | None:
    result = await db.execute(
        select(BusinessSetting.max_daily_bookings).where(
            BusinessSetting.business_id == business_id
        )
    )
    return result.scalar_one_or_none()


def _local_day_bounds(target_date: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) of ``target_date`` in business-local time, tz-aware."""
    day_start = datetime.combine(target_date, time(0, 0), tzinfo=tz)
    day_end = datetime.combine(target_date + timedelta(days=1), time(0, 0), tzinfo=tz)
    return day_start, day_end


async def _count_blocking_bookings_for_day(
    db: AsyncSession, business_id: UUID, target_date: date, tz: ZoneInfo
) -> int:
    day_start, day_end = _local_day_bounds(target_date, tz)
    result = await db.execute(
        select(func.count(Booking.id)).where(
            Booking.business_id == business_id,
            Booking.status.in_(_BLOCKING_STATUSES),
            Booking.deleted_at.is_(None),
            Booking.starts_at >= day_start,
            Booking.starts_at < day_end,
        )
    )
    return int(result.scalar_one())


async def _get_blocking_bookings_for_day(
    db: AsyncSession,
    business_id: UUID,
    target_date: date,
    tz: ZoneInfo,
) -> list[Booking]:
    """Bookings on `target_date` whose status blocks new slots."""
    # Day boundaries in business-local time. TZ-aware datetimes keep the
    # comparison unambiguous regardless of how the DB stores the column.
    # Matching on overlap with the day (not just starts_at) also catches a
    # booking that started before midnight and runs into this day.
    day_start, day_end = _local_day_bounds(target_date, tz)

    result = await db.execute(
        select(Booking).where(
            Booking.business_id == business_id,
            Booking.status.in_(_BLOCKING_STATUSES),
            Booking.deleted_at.is_(None),
            Booking.starts_at < day_end,
            Booking.ends_at > day_start,
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


def _to_local_naive(dt: datetime, tz: ZoneInfo) -> datetime:
    """Convert a stored booking timestamp to naive business-local time."""
    if dt.tzinfo is not None:
        return dt.astimezone(tz).replace(tzinfo=None)
    return dt  # naive: assume already business-local


def _busy_intervals(
    bookings: list[Booking], tz: ZoneInfo, buffer_minutes: int
) -> list[tuple[datetime, datetime]]:
    """Existing bookings as naive-local [start, end + buffer) intervals.

    The buffer is applied to the END of each existing booking too: a new
    slot must not start during another booking's buffer-out window.
    """
    pad = timedelta(minutes=buffer_minutes)
    return [
        (_to_local_naive(b.starts_at, tz), _to_local_naive(b.ends_at, tz) + pad)
        for b in bookings
    ]


def compute_slots(
    *,
    target_date: date,
    open_time: time,
    close_time: time,
    duration_minutes: int,
    buffer_minutes: int,
    busy_intervals: list[tuple[datetime, datetime]],
    now_local: datetime,
    time_window: str | None = None,
    limit: int = 3,
) -> list[Slot]:
    """Pure slot computation. No DB, no clock — everything is passed in."""
    if limit <= 0:
        return []

    block_minutes = duration_minutes + buffer_minutes
    grid = _generate_grid(
        target_date=target_date,
        open_time=open_time,
        close_time=close_time,
        duration_minutes=block_minutes,
    )

    window = _TIME_WINDOWS.get(time_window) if time_window else None

    survivors: list[Slot] = []
    for slot_start in grid:
        slot_end = slot_start + timedelta(minutes=block_minutes)

        if slot_start <= now_local:
            continue  # in the past or right now — not bookable

        if any(_overlaps(slot_start, slot_end, bs, be) for bs, be in busy_intervals):
            continue

        if window is not None:
            w_start, w_end = window
            if not (w_start <= slot_start.time() < w_end):
                continue

        survivors.append(
            Slot(
                start_local=slot_start,
                end_local=slot_start + timedelta(minutes=duration_minutes),
            )
        )
        if len(survivors) >= limit:
            break

    return survivors


def _business_tz(business: Business) -> ZoneInfo:
    try:
        return ZoneInfo(business.timezone)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Unknown business timezone %r; using UTC for booking lookups",
            business.timezone,
        )
        return ZoneInfo("UTC")


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

    Returns [] if the business is closed that day (weekly schedule or a
    schedule exception), the daily booking cap is reached, or every
    candidate slot conflicts with an existing booking.
    """
    if limit <= 0:
        return []

    tz = _business_tz(business)

    hours = await get_day_hours(db, business.id, target_date)
    if not hours.is_open or hours.open_time is None or hours.close_time is None:
        logger.info(
            "find_available_slots: business=%s closed on %s (reason=%r)",
            business.id,
            target_date,
            hours.reason,
        )
        return []

    max_daily = await _get_max_daily_bookings(db, business.id)
    if max_daily is not None:
        booked = await _count_blocking_bookings_for_day(db, business.id, target_date, tz)
        if booked >= max_daily:
            logger.info(
                "find_available_slots: business=%s at daily cap on %s (%d/%d)",
                business.id,
                target_date,
                booked,
                max_daily,
            )
            return []

    bookings = await _get_blocking_bookings_for_day(db, business.id, target_date, tz)
    survivors = compute_slots(
        target_date=target_date,
        open_time=hours.open_time,
        close_time=hours.close_time,
        duration_minutes=service.duration_minutes,
        buffer_minutes=service.buffer_minutes or 0,
        busy_intervals=_busy_intervals(bookings, tz, service.buffer_minutes or 0),
        now_local=datetime.now(tz=tz).replace(tzinfo=None),
        time_window=time_window,
        limit=limit,
    )

    logger.info(
        "find_available_slots: business=%s service=%r date=%s window=%r → %d slots",
        business.id,
        service.name,
        target_date,
        time_window,
        len(survivors),
    )
    return survivors


async def is_slot_still_available(
    db: AsyncSession,
    *,
    business: Business,
    service: Service,
    slot_start_local: datetime,
) -> bool:
    """Re-check one chosen start time right before a booking is written.

    Minutes can pass between offering a slot and the customer finishing
    their contact details; another customer may have taken it, or the
    admin may have closed the day. This re-runs the same rules as
    ``find_available_slots`` for exactly that start time.

    Note: this narrows the race window but cannot close it completely —
    two transactions checking at the same instant can both see the slot as
    free. A Postgres exclusion constraint on bookings would close it fully.
    """
    tz = _business_tz(business)
    target_date = slot_start_local.date()

    hours = await get_day_hours(db, business.id, target_date)
    if not hours.is_open or hours.open_time is None or hours.close_time is None:
        return False

    max_daily = await _get_max_daily_bookings(db, business.id)
    if max_daily is not None:
        booked = await _count_blocking_bookings_for_day(db, business.id, target_date, tz)
        if booked >= max_daily:
            return False

    bookings = await _get_blocking_bookings_for_day(db, business.id, target_date, tz)
    candidates = compute_slots(
        target_date=target_date,
        open_time=hours.open_time,
        close_time=hours.close_time,
        duration_minutes=service.duration_minutes,
        buffer_minutes=service.buffer_minutes or 0,
        busy_intervals=_busy_intervals(bookings, tz, service.buffer_minutes or 0),
        now_local=datetime.now(tz=tz).replace(tzinfo=None),
        limit=10_000,
    )
    return any(c.start_local == slot_start_local for c in candidates)
