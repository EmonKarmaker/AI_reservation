"""Date parser and slot matcher, with the LLM faked.

Checks how each one handles what the model sends back: clean answers,
chatty answers, NONE, garbage, invalid dates and API failures.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytest

from app.integrations.llm import LLMError
from app.services import booking_flow, date_parser
from app.services.booking_flow import _match_slot_choice
from app.services.date_parser import parse_booking_date


def _fake(reply: str | Exception):  # type: ignore[no-untyped-def]
    async def _call(messages: list[dict[str, str]], **_: Any) -> str:
        if isinstance(reply, Exception):
            raise reply
        return reply

    return _call


@pytest.mark.parametrize(
    ("llm_reply", "expected"),
    [
        ("2026-12-05", date(2026, 12, 5)),
        ("2026-12-05.", date(2026, 12, 5)),
        ("The date is 2026-12-05", date(2026, 12, 5)),
        ("NONE", None),
        ("none", None),
        ("next saturday", None),
        ("2026-02-30", None),  # not a real date
    ],
)
async def test_parse_booking_date(
    monkeypatch: pytest.MonkeyPatch, llm_reply: str, expected: date | None
) -> None:
    monkeypatch.setattr(date_parser, "chat_completion", _fake(llm_reply))
    result = await parse_booking_date(
        "Saturday", business_timezone="Asia/Dhaka", today=date(2026, 12, 1)
    )
    assert result == expected


async def test_parse_booking_date_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(date_parser, "chat_completion", _fake(LLMError("down")))
    assert await parse_booking_date("Saturday", business_timezone="Asia/Dhaka") is None


_OFFERED = [
    datetime(2026, 12, 5, 9, 0),
    datetime(2026, 12, 5, 9, 30),
    datetime(2026, 12, 5, 10, 0),
]


@pytest.mark.parametrize(
    ("llm_reply", "expected_index"),
    [("1", 0), ("2", 1), ("3.", 2), ("Slot 2", 1), ("NONE", None), ("4", None), ("x", None)],
)
async def test_match_slot_choice(
    monkeypatch: pytest.MonkeyPatch, llm_reply: str, expected_index: int | None
) -> None:
    monkeypatch.setattr(booking_flow, "chat_completion", _fake(llm_reply))
    result = await _match_slot_choice("the second one", _OFFERED)
    assert result == (None if expected_index is None else _OFFERED[expected_index])


async def test_match_slot_choice_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(booking_flow, "chat_completion", _fake(LLMError("down")))
    assert await _match_slot_choice("first", _OFFERED) is None


async def test_match_slot_choice_nothing_offered() -> None:
    assert await _match_slot_choice("first", []) is None
