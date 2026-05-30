"""LLM-based date extraction for the booking flow.

Why an LLM and not a deterministic parser:
- Customers say things like "Saturday morning", "next Friday", "the 7th",
  "in two weeks", "tomorrow". Off-the-shelf parsers (dateparser, python-dateutil)
  handle some of this but fail unpredictably on conversational phrasing.
- Latency cost (~1s on the fast Groq model) is acceptable for a step that
  happens once per booking conversation.
- We anchor the prompt with today's date in the business's local timezone
  so "Saturday" always resolves to the correct upcoming Saturday.

Validation lives in the booking_flow layer, not here. This module just
returns a date or None.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.integrations.llm import LLMError, chat_completion


logger = logging.getLogger(__name__)


_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


_DATE_PROMPT = """You extract a date from a customer's message to a booking \
chatbot.

Today is {today} ({weekday}) in {tz}.

Your job: figure out which calendar date the customer wants, then output \
ONLY that date in YYYY-MM-DD format. No explanation, no punctuation.

Rules:
- ANY day-of-week name (Monday, Tuesday, Wednesday, Thursday, Friday, \
Saturday, Sunday) means the next occurrence of that day on or after today.
- "next [day]" specifically means the day of NEXT week (7+ days away).
- "today" → today's date. "tomorrow" → today + 1 day.
- A month-and-day phrase ("June 7", "the 15th", "Dec 3") → that calendar \
date in the soonest future month where it hasn't passed yet.
- If the message contains no date reference, output: NONE
- If the message names multiple incompatible dates, output: NONE

Worked examples (assuming today is {today}, a {weekday}):
- "Monday" → next Monday on or after today
- "Monday morning" → same as above (ignore time-of-day)
- "next Monday" → the Monday 7+ days from today
- "tomorrow" → today + 1
- "June 7" → 2026-06-07 if today is on or before that, else 2027-06-07
- "the 15th" → 15th of this month (or next, if 15th has passed)
- "what's your cancellation policy?" → NONE
- "morning" → NONE (no day named)

Output ONLY YYYY-MM-DD or NONE."""


def today_in_business_tz(business_timezone: str) -> date:
    """Return today's date in the business's local timezone.

    Avoids the bug where the server runs in UTC but customers think in
    Asia/Dhaka — so "tomorrow" can be off by a day around midnight.
    """
    try:
        tz = ZoneInfo(business_timezone)
    except Exception:  # noqa: BLE001 — unknown tz string, fall back to UTC
        logger.warning("Unknown business timezone %r; falling back to UTC", business_timezone)
        tz = ZoneInfo("UTC")
    return datetime.now(tz=tz).date()


async def parse_booking_date(
    user_message: str,
    *,
    business_timezone: str,
    today: date | None = None,
) -> date | None:
    """Extract a booking date from a customer message.

    Returns None if no clear date was named (caller should re-ask) or if the
    LLM output couldn't be parsed.

    The returned date may still be invalid for the business (in the past,
    outside the booking window, on a closed day) — those checks live in
    the booking_flow handler.
    """
    if today is None:
        today = today_in_business_tz(business_timezone)

    system_prompt = _DATE_PROMPT.format(
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        tz=business_timezone,
    )

    try:
        # Use the smart model — date parsing is on the critical path of every
        # booking turn, so paying ~1-2s for reliability beats the fast model
        # silently returning NONE on phrasings it's never seen.
        raw = await chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.GROQ_MODEL_SMART,
            temperature=0.0,
            max_tokens=20,
        )
    except LLMError as exc:
        logger.warning("Date parser LLM call failed: %s", exc)
        return None

    cleaned = raw.strip().rstrip(".").strip("'\"")
    if cleaned.upper() == "NONE":
        return None

    match = _DATE_RE.search(cleaned)
    if not match:
        logger.info("Date parser: no YYYY-MM-DD in LLM output %r", raw[:60])
        return None

    try:
        parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        logger.info("Date parser: invalid date %r", match.group(0))
        return None

    logger.info("Date parser: %r → %s (today=%s)", user_message[:60], parsed, today)
    return parsed
