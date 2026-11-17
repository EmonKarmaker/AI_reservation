"""End-to-end booking flow tests (Phase 4.6.5 edge cases + 4.6.6d).

Each test drives the real LangGraph chat graph (run_chat_turn) against the
real database, turn by turn, exactly like the chat widget does. Only the
outside world is faked:

- Groq (intent classifier, date parser, slot matcher, RAG answer) — so
  tests are free, fast and deterministic;
- the embedding search for the service — so tests don't load MiniLM.

Like the other DB tests, rows are committed and left behind; every test
creates its own throwaway business with a unique slug.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import BookingStatus, BusinessStatus, DayOfWeek
from app.models.operating_hours import OperatingHours
from app.models.schedule_exception import ScheduleException
from app.models.service import Service
from app.services import booking_flow, chat_graph
from app.services.booking_flow import (
    STAGE_AWAITING_DATE,
    STAGE_AWAITING_SLOT,
    STAGE_COMPLETE,
)
from app.services.chat_graph import run_chat_turn

TZ = "Asia/Dhaka"


def _target_date() -> date:
    """A date safely in the future (all of its slots are bookable)."""
    return datetime.now(ZoneInfo(TZ)).date() + timedelta(days=3)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def biz(
    db_session: AsyncSession, unique_slug: Callable[[], str]
) -> tuple[Business, Service]:
    """A business open 09:00-18:00 every day with one 45-minute service."""
    business = Business(
        slug=unique_slug(),
        name="Test Dental",
        timezone=TZ,
        currency="BDT",
        status=BusinessStatus.ACTIVE,
    )
    db_session.add(business)
    await db_session.flush()
    db_session.add(BusinessSetting(business_id=business.id))
    for day in DayOfWeek:
        db_session.add(
            OperatingHours(
                business_id=business.id,
                day_of_week=day,
                open_time=time(9, 0),
                close_time=time(18, 0),
                is_closed=False,
            )
        )
    service = Service(
        business_id=business.id,
        name="Routine Cleaning",
        duration_minutes=45,
        price=Decimal("1500.00"),
        is_active=True,
    )
    db_session.add(service)
    await db_session.commit()
    return business, service


class FakeLLM:
    """Stands in for Groq. Records nothing; answers by prompt type."""

    def __init__(self) -> None:
        self.intent = "booking"
        self.slot_choice = "1"
        self.answer = "Our clinic is in Gulshan-2."

    async def __call__(self, messages: list[dict[str, str]], **_: Any) -> str:
        system = messages[0]["content"]
        if "You classify the customer's MOST RECENT message" in system:
            return self.intent
        if "Which slot did the customer pick?" in system:
            return self.slot_choice
        return self.answer


@pytest.fixture
def fake_llm(
    monkeypatch: pytest.MonkeyPatch, biz: tuple[Business, Service]
) -> FakeLLM:
    business, service = biz
    llm = FakeLLM()
    monkeypatch.setattr(chat_graph, "chat_completion", llm)
    monkeypatch.setattr(booking_flow, "chat_completion", llm)

    async def fake_parse_date(message: str, **_: Any) -> date | None:
        return _target_date() if "date please" in message else None

    async def fake_identify(db: AsyncSession, business_id: UUID, message: str):  # type: ignore[no-untyped-def]
        return service, []

    async def fake_retrieve(*_: Any, **__: Any) -> list[Any]:
        return []

    monkeypatch.setattr(booking_flow, "parse_booking_date", fake_parse_date)
    monkeypatch.setattr(booking_flow, "_identify_service", fake_identify)
    monkeypatch.setattr(chat_graph, "retrieve_relevant", fake_retrieve)
    return llm


class Chat:
    """One browser session talking to the bot."""

    def __init__(self, db: AsyncSession, business: Business) -> None:
        self.db = db
        self.business = business
        self.customer_id = uuid4()
        self.conversation_id: UUID | None = None

    async def say(self, message: str) -> str:
        state = await run_chat_turn(
            db=self.db,
            business_id=self.business.id,
            business_name=self.business.name,
            customer_id=self.customer_id,
            user_message=message,
        )
        self.conversation_id = state.conversation_id
        return state.assistant_message

    async def draft(self) -> dict[str, Any]:
        conversation = await self.db.get(
            Conversation, self.conversation_id, populate_existing=True
        )
        assert conversation is not None
        return dict((conversation.langgraph_state or {}).get("booking_draft") or {})

    async def bookings(self) -> list[Booking]:
        result = await self.db.execute(
            select(Booking)
            .where(Booking.customer_id == self.customer_id)
            .order_by(Booking.starts_at)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())


async def _walk_to_contact(chat: Chat) -> None:
    await chat.say("I want to book a cleaning")
    await chat.say("date please")
    await chat.say("the first one")
    assert (await chat.draft())["stage"] == booking_flow.STAGE_AWAITING_CONTACT


async def _give_contact(chat: Chat) -> str:
    await chat.say("John Doe")
    await chat.say("john@example.com")
    return await chat.say("+880 1712345678")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_full_booking_creates_row(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, service = biz
    chat = Chat(db_session, business)

    reply = await chat.say("I want to book a cleaning")
    assert "Routine Cleaning" in reply and "date" in reply.lower()

    reply = await chat.say("date please")
    assert "9:00 AM" in reply

    reply = await chat.say("the first one")
    assert "full name" in reply

    reply = await _give_contact(chat)
    assert "You're all set" in reply

    bookings = await chat.bookings()
    assert len(bookings) == 1
    booking = bookings[0]
    assert booking.status == BookingStatus.PENDING_PAYMENT
    assert booking.service_id == service.id
    assert booking.currency == "BDT"
    # 09:00 Asia/Dhaka (UTC+6) is 03:00 UTC.
    assert booking.starts_at.astimezone(ZoneInfo("UTC")).hour == 3
    assert booking.idempotency_key.startswith(f"chat:{chat.conversation_id}:")

    conversation = await db_session.get(
        Conversation, chat.conversation_id, populate_existing=True
    )
    assert conversation is not None and conversation.booking_id == booking.id

    customer = await db_session.get(Customer, chat.customer_id, populate_existing=True)
    assert customer is not None
    assert customer.full_name == "John Doe"
    assert customer.email == "john@example.com"
    assert (await chat.draft())["stage"] == STAGE_COMPLETE


# ---------------------------------------------------------------------------
# Second booking in the same chat
# ---------------------------------------------------------------------------


async def test_second_booking_same_chat_reuses_contact(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    chat = Chat(db_session, business)
    await _walk_to_contact(chat)
    await _give_contact(chat)

    # Previously this replied "Thanks! The team will reach out" and booked nothing.
    reply = await chat.say("Can I also book another cleaning?")
    assert "date" in reply.lower()
    await chat.say("date please")
    reply = await chat.say("the first one")  # 09:00-09:45 is taken, so this is 10:00

    assert "You're all set" in reply  # contact details were not asked again
    bookings = await chat.bookings()
    assert len(bookings) == 2
    assert bookings[0].idempotency_key != bookings[1].idempotency_key
    assert bookings[1].starts_at - bookings[0].starts_at == timedelta(minutes=60)


# ---------------------------------------------------------------------------
# Slot taken between offer and finalize
# ---------------------------------------------------------------------------


async def test_slot_taken_before_finalize_offers_new_times(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, service = biz
    chat = Chat(db_session, business)
    await _walk_to_contact(chat)
    chosen = datetime.fromisoformat((await chat.draft())["slot_start_at"])

    # Another customer grabs the same 09:00 slot in the meantime.
    other = Customer(business_id=business.id, full_name="Other", email="other@example.com")
    db_session.add(other)
    await db_session.flush()
    start_utc = chosen.replace(tzinfo=ZoneInfo(TZ)).astimezone(ZoneInfo("UTC"))
    db_session.add(
        Booking(
            business_id=business.id,
            customer_id=other.id,
            service_id=service.id,
            starts_at=start_utc,
            ends_at=start_utc + timedelta(minutes=45),
            status=BookingStatus.CONFIRMED,
            total_amount=Decimal("1500.00"),
            currency="BDT",
            idempotency_key=f"test:{uuid4()}",
        )
    )
    await db_session.commit()

    reply = await _give_contact(chat)
    assert "was just taken" in reply
    assert "9:00 AM" not in reply.split("open on")[-1]
    draft = await chat.draft()
    assert draft["stage"] == STAGE_AWAITING_SLOT
    assert chosen.isoformat() not in draft["offered_slots"]
    assert await chat.bookings() == []

    reply = await chat.say("the first one")
    assert "You're all set" in reply  # contact kept, booked straight away
    bookings = await chat.bookings()
    assert len(bookings) == 1 and bookings[0].starts_at != start_utc


# ---------------------------------------------------------------------------
# Closed days
# ---------------------------------------------------------------------------


async def test_holiday_exception_closes_the_day(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    db_session.add(
        ScheduleException(
            business_id=business.id,
            exception_date=_target_date(),
            is_closed=True,
            reason="Victory Day",
        )
    )
    await db_session.commit()

    chat = Chat(db_session, business)
    await chat.say("I want to book a cleaning")
    reply = await chat.say("date please")

    assert "closed" in reply and "Victory Day" in reply
    assert (await chat.draft())["stage"] == STAGE_AWAITING_DATE


async def test_special_hours_exception_limits_slots(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    db_session.add(
        ScheduleException(
            business_id=business.id,
            exception_date=_target_date(),
            is_closed=False,
            open_time=time(14, 0),
            close_time=time(15, 0),
            reason="Half day",
        )
    )
    await db_session.commit()

    chat = Chat(db_session, business)
    await chat.say("I want to book a cleaning")
    reply = await chat.say("date please")

    assert "2:00 PM" in reply and "9:00 AM" not in reply


async def test_daily_cap_reached(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    settings_row = (
        await db_session.execute(
            select(BusinessSetting).where(BusinessSetting.business_id == business.id)
        )
    ).scalar_one()
    settings_row.max_daily_bookings = 1
    await db_session.commit()

    first = Chat(db_session, business)
    await _walk_to_contact(first)
    await _give_contact(first)

    second = Chat(db_session, business)
    await second.say("I want to book a cleaning")
    reply = await second.say("date please")
    assert "fully booked" in reply


# ---------------------------------------------------------------------------
# Side questions mid-booking (4.6.6d) and cancellation
# ---------------------------------------------------------------------------


async def test_side_question_answered_and_draft_kept(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    chat = Chat(db_session, business)
    await chat.say("I want to book a cleaning")
    before = await chat.draft()

    fake_llm.intent = "question"
    reply = await chat.say("Where are you located?")
    assert reply.startswith("Our clinic is in Gulshan-2.")
    assert "what date would you like for your Routine Cleaning" in reply
    assert await chat.draft() == before

    # A short answer is still forced into the booking flow (sticky routing).
    reply = await chat.say("date please")
    assert "9:00 AM" in reply


async def test_cancel_mid_booking_clears_draft(
    db_session: AsyncSession, biz: tuple[Business, Service], fake_llm: FakeLLM
) -> None:
    business, _ = biz
    chat = Chat(db_session, business)
    await chat.say("I want to book a cleaning")
    await chat.say("date please")

    reply = await chat.say("actually, nevermind")
    assert "cancelled" in reply
    assert await chat.draft() == {}
    assert await chat.bookings() == []
