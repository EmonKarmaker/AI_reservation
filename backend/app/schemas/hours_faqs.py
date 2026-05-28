"""Admin schemas for operating hours, schedule exceptions, and FAQs."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DayOfWeek


# ---------------------------------------------------------------------------
# Operating hours
# ---------------------------------------------------------------------------

class OperatingHoursDay(BaseModel):
    """One day's hours. open_time/close_time may be null when is_closed=True."""

    model_config = ConfigDict(from_attributes=True)

    day_of_week: DayOfWeek
    open_time: time | None = None
    close_time: time | None = None
    is_closed: bool = False


class OperatingHoursOut(BaseModel):
    """The full weekly grid (up to 7 entries)."""

    days: list[OperatingHoursDay]


class OperatingHoursReplace(BaseModel):
    """PUT body: replace the entire weekly grid in one shot.

    Each day_of_week may appear at most once. Days omitted from the list are
    left untouched (not deleted), so a partial submission is allowed but the
    frontend will normally send all 7.
    """

    days: list[OperatingHoursDay] = Field(..., min_length=1, max_length=7)


# ---------------------------------------------------------------------------
# Schedule exceptions
# ---------------------------------------------------------------------------

class ScheduleExceptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    exception_date: date
    is_closed: bool
    open_time: time | None
    close_time: time | None
    reason: str | None


class ScheduleExceptionCreate(BaseModel):
    exception_date: date
    is_closed: bool = True
    open_time: time | None = None
    close_time: time | None = None
    reason: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# FAQs
# ---------------------------------------------------------------------------

class FaqOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    business_id: UUID
    question: str
    answer: str
    category: str | None
    is_active: bool
    display_order: int


class FaqCreate(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=5000)
    category: str | None = Field(default=None, max_length=80)
    is_active: bool = Field(default=True)
    display_order: int = Field(default=0, ge=0)


class FaqUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=500)
    answer: str | None = Field(default=None, min_length=1, max_length=5000)
    category: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0)
