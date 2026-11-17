"""Unit tests for the booking flow's pure helpers.

No database, no network, no LLM. These run in milliseconds and cover the
parsing/validation rules the chatbot relies on every turn.
"""

from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace

import pytest

from app.integrations.llm import (
    REASONING_MIN_TOKENS,
    build_completion_kwargs,
    clean_completion_text,
    is_reasoning_model,
)
from app.services.booking_flow import (
    STAGE_AWAITING_CONTACT,
    STAGE_AWAITING_DATE,
    STAGE_AWAITING_SERVICE,
    STAGE_AWAITING_SLOT,
    STAGE_COMPLETE,
    _extract_email,
    _extract_name,
    _extract_phone,
    _get_booking_draft,
    _is_cancellation_intent,
    booking_resume_prompt,
    get_active_booking_stage,
)
from app.services.chat_graph import _parse_intent, looks_like_side_question
from app.services.slot_finder import (
    compute_slots,
    extract_time_window,
    resolve_hours,
)

# ---------------------------------------------------------------------------
# Contact extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("John Doe", "John Doe"),
        ("my name is John Doe", "John Doe"),
        ("Hi, I'm Emon Karmoker", "Emon Karmoker"),
        ("I am Fatima Rahman.", "Fatima Rahman"),
        ("call me Madonna", "Madonna"),
        ("Sheikh Mohammed bin Rashid Al Maktoum", "Sheikh Mohammed bin Rashid Al Maktoum"),
        ("Jane Booker", "Jane Booker"),  # 'book' inside a surname is fine
    ],
)
def test_extract_name_accepts_names(message: str, expected: str) -> None:
    assert _extract_name(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "",
        "   ",
        "a",
        "12345",
        "I want to book a routine cleaning",
        "can I schedule an appointment",
        "hi there",
        "one two three four five six seven",
    ],
)
def test_extract_name_rejects_non_names(message: str) -> None:
    assert _extract_name(message) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("john@example.com", "john@example.com"),
        ("It's John.Doe+test@Example.COM thanks", "john.doe+test@example.com"),
        ("email me at a.b@sub.domain.co", "a.b@sub.domain.co"),
    ],
)
def test_extract_email(message: str, expected: str) -> None:
    assert _extract_email(message) == expected


@pytest.mark.parametrize("message", ["john at example dot com", "john@", "@example.com", "hello"])
def test_extract_email_rejects(message: str) -> None:
    assert _extract_email(message) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("01712345678", "01712345678"),
        ("+880 1712-345678", "+8801712345678"),
        ("(017) 1234 5678", "01712345678"),
    ],
)
def test_extract_phone(message: str, expected: str) -> None:
    assert _extract_phone(message) == expected


@pytest.mark.parametrize("message", ["12345", "call me maybe", "1234567890123456", "+"])
def test_extract_phone_rejects(message: str) -> None:
    assert _extract_phone(message) is None


# ---------------------------------------------------------------------------
# Cancellation detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "nevermind",
        "never mind",
        "cancel",
        "Cancel the booking",
        "forget it",
        "forget about the booking",
        "start over",
        "reset",
        "no thanks",
        "I don't want to",
        "actually, nevermind",
    ],
)
def test_cancellation_detected(message: str) -> None:
    assert _is_cancellation_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "John Doe",
        "I want to book a routine cleaning",
        "Monday morning",
        "what's your cancellation policy?",
        "",
    ],
)
def test_cancellation_not_detected(message: str) -> None:
    assert _is_cancellation_intent(message) is False


# ---------------------------------------------------------------------------
# Draft helpers
# ---------------------------------------------------------------------------


def _conv(state: dict | None) -> SimpleNamespace:
    return SimpleNamespace(langgraph_state=state)


def test_get_booking_draft_returns_copy() -> None:
    inner = {"stage": STAGE_AWAITING_DATE}
    conversation = _conv({"booking_draft": inner})
    draft = _get_booking_draft(conversation)  # type: ignore[arg-type]
    draft["stage"] = "mutated"
    assert inner["stage"] == STAGE_AWAITING_DATE  # Gotcha 25: must be a copy


@pytest.mark.parametrize("state", [None, {}, {"booking_draft": "bad"}])
def test_get_booking_draft_handles_missing(state: dict | None) -> None:
    assert _get_booking_draft(_conv(state)) == {}  # type: ignore[arg-type]


def test_active_stage_none_when_complete() -> None:
    conversation = _conv({"booking_draft": {"stage": STAGE_COMPLETE}})
    assert get_active_booking_stage(conversation) is None  # type: ignore[arg-type]


def test_resume_prompt_per_stage() -> None:
    def prompt(draft: dict) -> str | None:
        return booking_resume_prompt(_conv({"booking_draft": draft}))  # type: ignore[arg-type]

    assert prompt({}) is None
    assert prompt({"stage": STAGE_COMPLETE}) is None
    assert "which service" in (prompt({"stage": STAGE_AWAITING_SERVICE}) or "")
    assert "Routine Cleaning" in (
        prompt({"stage": STAGE_AWAITING_DATE, "service_name": "Routine Cleaning"}) or ""
    )
    slot_prompt = prompt(
        {"stage": STAGE_AWAITING_SLOT, "offered_slots": ["2026-12-01T09:00:00"]}
    ) or ""
    assert "9:00 AM" in slot_prompt
    assert "full name" in (prompt({"stage": STAGE_AWAITING_CONTACT}) or "")
    assert "email" in (
        prompt({"stage": STAGE_AWAITING_CONTACT, "customer_name": "John"}) or ""
    )
    assert "phone" in (
        prompt(
            {
                "stage": STAGE_AWAITING_CONTACT,
                "customer_name": "John",
                "customer_email": "j@example.com",
            }
        )
        or ""
    )


# ---------------------------------------------------------------------------
# Intent parsing and side questions (4.6.6d)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("booking", "booking"),
        (" Booking.", "booking"),
        ("escalate", "escalate"),
        ("question - asking about price", "question"),
        ("gibberish", "question"),
        ("", "question"),
    ],
)
def test_parse_intent(raw: str, expected: str) -> None:
    assert _parse_intent(raw) == expected


@pytest.mark.parametrize(
    "message",
    [
        "How long does a root canal take?",
        "do you accept insurance?",
        "Where are you located?",
        "What's your cancellation policy?",
        "Why do you need my phone number?",
    ],
)
def test_side_questions_detected(message: str) -> None:
    assert looks_like_side_question(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "Saturday",
        "10:30",
        "the first one",
        "Can I come on Saturday?",
        "is 10:30 free?",
        "what about tomorrow morning?",
        "any slots next week?",
        "John Doe",
        "john@example.com",
        "+880 1712345678",
        "ok?",
        "what times do you have",
    ],
)
def test_booking_answers_not_side_questions(message: str) -> None:
    assert looks_like_side_question(message) is False


# ---------------------------------------------------------------------------
# LLM wrapper (reasoning models)
# ---------------------------------------------------------------------------


def test_reasoning_model_detection() -> None:
    assert is_reasoning_model("openai/gpt-oss-20b")
    assert is_reasoning_model("openai/gpt-oss-120b")
    assert is_reasoning_model("qwen/qwen3.6-27b")
    assert not is_reasoning_model("llama-3.3-70b-versatile")


def test_completion_kwargs_raise_budget_for_reasoning_models() -> None:
    kwargs = build_completion_kwargs(
        model="openai/gpt-oss-20b", messages=[], temperature=0.0, max_tokens=10
    )
    assert kwargs["max_tokens"] == REASONING_MIN_TOKENS
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["include_reasoning"] is False


def test_completion_kwargs_untouched_for_plain_models() -> None:
    kwargs = build_completion_kwargs(
        model="some-plain-model", messages=[], temperature=0.0, max_tokens=10
    )
    assert kwargs["max_tokens"] == 10
    assert "reasoning_effort" not in kwargs


def test_clean_completion_text_strips_think_blocks() -> None:
    assert clean_completion_text("<think>hmm</think>\nbooking") == "booking"
    assert clean_completion_text("  question ") == "question"


# ---------------------------------------------------------------------------
# Slot finder (pure parts)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Saturday morning", "morning"),
        ("in the afternoon please", "afternoon"),
        ("evening", "evening"),
        ("tonight", "evening"),
        ("Saturday", None),
    ],
)
def test_extract_time_window(message: str, expected: str | None) -> None:
    assert extract_time_window(message) == expected


def _hours(open_t: time, close_t: time, closed: bool = False) -> SimpleNamespace:
    return SimpleNamespace(open_time=open_t, close_time=close_t, is_closed=closed)


def _exception(
    closed: bool, open_t: time | None = None, close_t: time | None = None, reason: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(is_closed=closed, open_time=open_t, close_time=close_t, reason=reason)


def test_resolve_hours_weekly_only() -> None:
    day = resolve_hours(_hours(time(9), time(18)), None)  # type: ignore[arg-type]
    assert day.is_open and day.open_time == time(9) and day.close_time == time(18)


def test_resolve_hours_closed_weekday() -> None:
    assert not resolve_hours(_hours(time(0), time(0), closed=True), None).is_open  # type: ignore[arg-type]
    assert not resolve_hours(None, None).is_open


def test_resolve_hours_holiday_closure_wins() -> None:
    day = resolve_hours(
        _hours(time(9), time(18)),  # type: ignore[arg-type]
        _exception(True, reason="Eid holiday"),  # type: ignore[arg-type]
    )
    assert not day.is_open
    assert day.reason == "Eid holiday"


def test_resolve_hours_special_hours_win() -> None:
    day = resolve_hours(
        _hours(time(9), time(18)),  # type: ignore[arg-type]
        _exception(False, time(10), time(13)),  # type: ignore[arg-type]
    )
    assert day.is_open and day.open_time == time(10) and day.close_time == time(13)


def test_resolve_hours_exception_opens_normally_closed_day() -> None:
    day = resolve_hours(
        _hours(time(0), time(0), closed=True),  # type: ignore[arg-type]
        _exception(False, time(10), time(12)),  # type: ignore[arg-type]
    )
    assert day.is_open


def test_resolve_hours_bad_exception_times_mean_closed() -> None:
    day = resolve_hours(
        _hours(time(9), time(18)),  # type: ignore[arg-type]
        _exception(False, time(13), time(10)),  # type: ignore[arg-type]
    )
    assert not day.is_open


_DAY = date(2030, 1, 7)
_EARLY = datetime(2030, 1, 1, 0, 0)


def _slots(**overrides):  # type: ignore[no-untyped-def]
    params = {
        "target_date": _DAY,
        "open_time": time(9),
        "close_time": time(12),
        "duration_minutes": 45,
        "buffer_minutes": 0,
        "busy_intervals": [],
        "now_local": _EARLY,
        "time_window": None,
        "limit": 10,
    }
    params.update(overrides)
    return [s.start_local.strftime("%H:%M") for s in compute_slots(**params)]


def test_compute_slots_grid_respects_close_time() -> None:
    # 45-min service, 9-12: last start that fits is 11:00.
    assert _slots() == ["09:00", "09:30", "10:00", "10:30", "11:00"]


def test_compute_slots_buffer_shrinks_day() -> None:
    # 45 + 30 buffer = 75 min block: last start that fits is 10:30.
    assert _slots(buffer_minutes=30) == ["09:00", "09:30", "10:00", "10:30"]


def test_compute_slots_skips_conflicts() -> None:
    busy = [(datetime(2030, 1, 7, 10, 0), datetime(2030, 1, 7, 10, 45))]
    # 09:30 + 45 = 10:15 overlaps; 10:00, 10:30 overlap; 11:00 is clear.
    assert _slots(busy_intervals=busy) == ["09:00", "11:00"]


def test_compute_slots_back_to_back_is_allowed() -> None:
    busy = [(datetime(2030, 1, 7, 9, 0), datetime(2030, 1, 7, 9, 30))]
    assert _slots(busy_intervals=busy)[0] == "09:30"


def test_compute_slots_skips_past_times() -> None:
    assert _slots(now_local=datetime(2030, 1, 7, 10, 0)) == ["10:30", "11:00"]


def test_compute_slots_time_window() -> None:
    assert _slots(close_time=time(18), time_window="afternoon", limit=2) == ["12:00", "12:30"]
    assert _slots(close_time=time(18), time_window="evening") == ["17:00"]
    assert _slots(time_window="evening") == []  # closes at noon


def test_compute_slots_limit() -> None:
    assert len(_slots(limit=3)) == 3
    assert _slots(limit=0) == []


def test_compute_slots_service_longer_than_day() -> None:
    assert _slots(duration_minutes=240) == []
