"""Multi-turn booking flow for the AI receptionist.

Phase 4.6 replaces the booking_stub_node (polite deferral) with a real
state machine that walks a customer through:
    service selection → date extraction → slot picking
    → contact collection → booking creation.

State is persisted in ``conversations.langgraph_state["booking_draft"]``
(JSONB). Each call to ``booking_node`` reads the current draft, dispatches
based on ``stage``, persists the updated draft, and returns the assistant
reply for this turn.

Why a single dispatcher (not a sub-graph):
- Keeps the top-level chat graph flat — one node per intent.
- Stages are linear and small; conditional-edge complexity isn't worth it.
- Future refactor to a real sub-graph is straightforward if needed.

Phase 4.6.1 (this commit) implements ONLY the ``awaiting_service`` stage.
Other stages return a polite placeholder until 4.6.2+.

Multi-tenancy: every DB read is scoped to ``state.business_id``. There is
no path through this module that allows cross-tenant data leakage.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.llm import LLMError, chat_completion
from app.models.booking import Booking
from app.models.business import Business
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import BookingStatus, EmbeddingSourceType
from app.models.service import Service
from app.services.date_parser import parse_booking_date, today_in_business_tz
from app.services.rag import retrieve_relevant
from app.services.slot_finder import Slot, extract_time_window, find_available_slots

if TYPE_CHECKING:
    from datetime import date as date_type
    from app.services.chat_graph import ChatState


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage constants
# ---------------------------------------------------------------------------
# Stored in booking_draft["stage"]. Strings rather than an Enum so the JSONB
# round-trips cleanly without custom converters.

STAGE_AWAITING_SERVICE = "awaiting_service"
STAGE_AWAITING_DATE = "awaiting_date"
STAGE_AWAITING_SLOT = "awaiting_slot"
STAGE_AWAITING_CONTACT = "awaiting_contact"
STAGE_COMPLETE = "complete"


# ---------------------------------------------------------------------------
# Service-matching heuristics
# ---------------------------------------------------------------------------
# pgvector cosine distance is in [0, 2]. For MiniLM-encoded service names,
# observed values: identical phrasing ~0.0-0.1; closely related (e.g.
# "routine cleaning" vs "dental cleaning") ~0.15-0.35; loosely related
# ~0.4-0.6; unrelated ~0.7+.
#
# A "strong" match is one we'll commit to without asking. Above the strong
# threshold we present alternatives.
SERVICE_STRONG_MATCH_THRESHOLD = 0.4

# If the top match is strong, but the runner-up is within this gap, the
# user's wording is ambiguous between the two — ask to disambiguate.
SERVICE_AMBIGUOUS_GAP = 0.10

# When showing alternatives because we couldn't confidently match, only
# include services whose distance is at least below this looser cutoff.
# Beyond this, the service is too far afield to suggest.
SERVICE_SUGGESTION_CUTOFF = 0.7


# ---------------------------------------------------------------------------
# Draft state helpers
# ---------------------------------------------------------------------------

def _get_booking_draft(conversation: Conversation) -> dict:
    """Return a COPY of the booking_draft sub-dict from langgraph_state.

    Defensive: langgraph_state has a JSONB server_default of '{}', but for
    older conversations or weird states it could theoretically be None.

    CRITICAL: returns a COPY of the inner dict, not a reference. This is the
    other half of the JSONB mutation-tracking trap (see _save_booking_draft
    for the save-time half).

    If we returned a live reference, the caller would mutate it in place
    when they set draft["service_id"] etc. That mutation would silently
    update SQLAlchemy's committed_state too, since committed_state holds a
    reference to that exact dict. The next flush would then compare
    "current == committed" by value (both holding the same mutated data)
    and SKIP the write.

    The bug is invisible on fresh conversations (langgraph_state = {} on
    server-default, so we return a brand-new {} that's not aliased to
    anything) but fires every time we resume an existing draft. Caller can
    now mutate the returned dict freely; nothing persists until
    _save_booking_draft is explicitly called.
    """
    state = conversation.langgraph_state or {}
    draft = state.get("booking_draft")
    if not isinstance(draft, dict):
        return {}
    return dict(draft)  # COPY — see CRITICAL note above


def get_active_booking_stage(conversation: Conversation) -> str | None:
    """Return the current booking stage, or None if no booking is in progress.

    Used by chat_graph to decide whether to make the booking flow "sticky" —
    when a booking is in progress, ambiguous user messages should keep
    routing to the booking flow instead of being treated as new questions.

    Returns None if no draft, or if the draft is at the COMPLETE stage.
    """
    draft = _get_booking_draft(conversation)
    stage = draft.get("stage")
    if not stage or stage == STAGE_COMPLETE:
        return None
    return stage


async def _save_booking_draft(
    db: AsyncSession,
    conversation: Conversation,
    draft: dict,
) -> None:
    """Persist booking_draft back into conversations.langgraph_state.

    We REPLACE the whole top-level dict (rather than mutating in place) so
    SQLAlchemy's change-detection sees the update. In-place mutation of
    JSONB columns is famously not detected without sqlalchemy.ext.mutable.

    CRITICAL: we COPY `draft` (dict(draft)) rather than store a reference,
    so SQLAlchemy's committed_state holds an isolated snapshot. Without the
    copy, subsequent in-place mutations of the caller's `draft` variable
    also silently mutate committed_state. The next flush then compares
    "current == committed" as True (same contents) and SKIPS the write —
    so all writes after the first per-turn save are silently lost.

    Only the booking_draft sub-key is touched; other state keys are preserved.
    """
    state = dict(conversation.langgraph_state or {})
    state["booking_draft"] = dict(draft)  # snapshot copy — see CRITICAL comment
    conversation.langgraph_state = state
    # Flush so the change is in the transaction; save_turn_node will commit
    # it alongside the message inserts at end of turn.
    await db.flush()


# ---------------------------------------------------------------------------
# Service-listing helpers
# ---------------------------------------------------------------------------

async def _list_active_services(
    db: AsyncSession, business_id: UUID
) -> list[Service]:
    """All active, non-deleted services for the business, ordered for menu display."""
    result = await db.execute(
        select(Service)
        .where(
            Service.business_id == business_id,
            Service.is_active.is_(True),
            Service.deleted_at.is_(None),
        )
        .order_by(Service.display_order, Service.name)
    )
    return list(result.scalars().all())


def _format_service_menu(services: list[Service]) -> str:
    """Render a list of services as a friendly bullet menu for chat."""
    if not services:
        return ""
    return "\n".join(f"- {s.name}" for s in services)


# ---------------------------------------------------------------------------
# Service identification via RAG
# ---------------------------------------------------------------------------

async def _identify_service(
    db: AsyncSession,
    business_id: UUID,
    user_message: str,
) -> tuple[Service | None, list[Service]]:
    """Try to identify which service the customer wants.

    Returns ``(matched_service_or_None, alternatives)``.

    - ``matched_service != None`` → confident single match. Caller should
      commit to it and advance the draft.
    - ``matched_service is None`` and ``alternatives`` non-empty → ambiguous
      or weak match. Caller should ask the customer to choose between the
      alternatives.
    - ``matched_service is None`` and ``alternatives`` empty → nothing
      relevant came back. Caller should fall back to listing all active
      services.

    Heuristic outline (thresholds tunable as module constants):
    - Top hit's distance > STRONG_THRESHOLD → not confident, return
      alternatives (anything below SUGGESTION_CUTOFF).
    - Top hit is strong but runner-up is within AMBIGUOUS_GAP → ambiguous,
      return both as alternatives.
    - Otherwise → return the matched service.
    """
    chunks = await retrieve_relevant(
        db,
        business_id=business_id,
        query=user_message,
        top_k=5,
        source_types=[EmbeddingSourceType.SERVICE],
    )

    if not chunks:
        return None, []

    best = chunks[0]

    # --- Case 1: top match is too weak ------------------------------------
    if best.distance > SERVICE_STRONG_MATCH_THRESHOLD:
        candidate_ids = [
            c.source_id for c in chunks if c.distance <= SERVICE_SUGGESTION_CUTOFF
        ]
        if not candidate_ids:
            return None, []
        alts = await _load_services_by_ids(db, business_id, candidate_ids)
        # If only one service survives the cutoff + active filter, treat it
        # as the answer rather than a one-item disambiguation. Common case:
        # the customer's phrasing ("I want to book a X") puts MiniLM's
        # distance to the service ~0.4-0.5 because of the extra framing
        # words, but no other service is even remotely relevant.
        if len(alts) == 1:
            return alts[0], []
        return None, alts

    # --- Case 2: top match is strong, but runner-up is close --------------
    runner_up = chunks[1].distance if len(chunks) > 1 else float("inf")
    if runner_up - best.distance < SERVICE_AMBIGUOUS_GAP:
        ambiguous_ids = [
            c.source_id
            for c in chunks
            if c.distance - best.distance < SERVICE_AMBIGUOUS_GAP
        ]
        alts = await _load_services_by_ids(db, business_id, ambiguous_ids)
        # If only one of them survives the active+not-deleted filter, treat
        # it as a confident match after all.
        if len(alts) == 1:
            return alts[0], []
        return None, alts

    # --- Case 3: strong, unambiguous match --------------------------------
    matched = await _load_service_by_id(db, business_id, best.source_id)
    if matched is None:
        # Edge case: embedding exists but service was deleted/deactivated.
        # Fall back to alternatives.
        candidate_ids = [
            c.source_id for c in chunks[1:] if c.distance <= SERVICE_SUGGESTION_CUTOFF
        ]
        alts = await _load_services_by_ids(db, business_id, candidate_ids)
        return None, alts

    return matched, []


async def _load_service_by_id(
    db: AsyncSession, business_id: UUID, service_id: UUID
) -> Service | None:
    """Fetch one service, respecting tenant scope + active/non-deleted."""
    result = await db.execute(
        select(Service).where(
            Service.id == service_id,
            Service.business_id == business_id,
            Service.is_active.is_(True),
            Service.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _load_services_by_ids(
    db: AsyncSession, business_id: UUID, service_ids: list[UUID]
) -> list[Service]:
    """Fetch multiple services, preserving the requested order, scoped."""
    if not service_ids:
        return []
    result = await db.execute(
        select(Service).where(
            Service.id.in_(service_ids),
            Service.business_id == business_id,
            Service.is_active.is_(True),
            Service.deleted_at.is_(None),
        )
    )
    by_id = {s.id: s for s in result.scalars().all()}
    # Preserve the input order (which came from RAG distance order).
    return [by_id[sid] for sid in service_ids if sid in by_id]


# ---------------------------------------------------------------------------
# Dispatcher node
# ---------------------------------------------------------------------------

async def booking_node(state: "ChatState") -> dict:
    """Multi-stage booking flow dispatcher.

    Reads booking_draft from langgraph_state, dispatches based on ``stage``,
    persists the updated draft, returns the assistant reply.

    Failure modes are best-effort: any error here returns a graceful reply
    asking the customer to try again rather than propagating an exception
    that would break the chat.
    """
    if state.conversation_id is None:
        logger.warning("booking_node: no conversation_id in state")
        return {
            "assistant_message": (
                "I had trouble starting the booking. Could you try again in a moment?"
            )
        }

    # Load the conversation. SQLAlchemy's identity map will hand back the
    # same instance load_history_node already loaded, so subsequent writes
    # to .langgraph_state apply to the right object.
    result = await state.db.execute(
        select(Conversation).where(Conversation.id == state.conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        logger.warning(
            "booking_node: conversation %s not found in DB", state.conversation_id
        )
        return {
            "assistant_message": (
                "I lost track of our conversation. Could you start the booking "
                "request again?"
            )
        }

    draft = _get_booking_draft(conversation)
    stage = draft.get("stage", STAGE_AWAITING_SERVICE)

    logger.info(
        "booking_node: business=%s, conversation=%s, stage=%s",
        state.business_id,
        state.conversation_id,
        stage,
    )

    if stage == STAGE_AWAITING_SERVICE:
        return await _handle_awaiting_service(state, conversation, draft)
    if stage == STAGE_AWAITING_DATE:
        return await _handle_awaiting_date(state, conversation, draft)
    if stage == STAGE_AWAITING_SLOT:
        return await _handle_awaiting_slot(state, conversation, draft)
    if stage == STAGE_AWAITING_CONTACT:
        return await _handle_awaiting_contact(state, conversation, draft)

    # STAGE_COMPLETE — actual Booking row creation lands in 4.6.4. For now,
    # if we somehow reach this stage, give a polite acknowledgement.
    return {
        "assistant_message": (
            f"Thanks! The {state.business_name} team will reach out shortly "
            "to confirm your booking. Anything else I can help with?"
        )
    }


async def _handle_awaiting_service(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> dict:
    """Identify the requested service or ask the customer to pick one."""
    # Persist the stage marker BEFORE we know this turn's outcome, so that
    # sticky routing in chat_graph fires on the NEXT turn even when this
    # turn ends in disambiguation (no service picked yet, no other state to
    # persist). Without this, the draft stays {} and follow-up messages
    # like "Routine Cleaning" or "Monday" get re-classified as questions.
    if draft.get("stage") != STAGE_AWAITING_SERVICE:
        draft["stage"] = STAGE_AWAITING_SERVICE
        await _save_booking_draft(state.db, conversation, draft)

    matched, alternatives = await _identify_service(
        state.db, state.business_id, state.user_message
    )

    if matched is not None:
        # Confident match. Advance the draft.
        draft["service_id"] = str(matched.id)
        draft["service_name"] = matched.name
        draft["stage"] = STAGE_AWAITING_DATE
        await _save_booking_draft(state.db, conversation, draft)

        logger.info(
            "booking_node: service selected — name=%r id=%s",
            matched.name,
            matched.id,
        )
        return {
            "assistant_message": (
                f"Got it — {matched.name}. What date works for you?"
            )
        }

    # No confident match. Either show ambiguous alternatives or all services.
    if alternatives:
        menu = _format_service_menu(alternatives)
        logger.info(
            "booking_node: ambiguous — %d alternatives offered", len(alternatives)
        )
        return {
            "assistant_message": (
                "I want to make sure I book the right service. Which of these "
                f"did you have in mind?\n\n{menu}"
            )
        }

    # Nothing matched — fall back to listing every active service.
    all_services = await _list_active_services(state.db, state.business_id)
    if not all_services:
        logger.warning(
            "booking_node: business=%s has no active services to offer",
            state.business_id,
        )
        return {
            "assistant_message": (
                f"I don't see any bookable services right now. Let me get a "
                f"team member from {state.business_name} to follow up with you."
            )
        }

    menu = _format_service_menu(all_services)
    logger.info(
        "booking_node: no RAG match — listing all %d services", len(all_services)
    )
    return {
        "assistant_message": (
            "Happy to help you book! Which service would you like?\n\n"
            f"{menu}"
        )
    }


# ---------------------------------------------------------------------------
# Date stage
# ---------------------------------------------------------------------------

async def _load_business(db: AsyncSession, business_id) -> Business | None:
    result = await db.execute(select(Business).where(Business.id == business_id))
    return result.scalar_one_or_none()


async def _load_service(
    db: AsyncSession, business_id, service_id_str: str
) -> Service | None:
    """Re-load the service stored in the draft, scoped by tenant + active."""
    from uuid import UUID as _UUID  # local import to avoid top-level noise

    try:
        sid = _UUID(service_id_str)
    except (TypeError, ValueError):
        return None
    return await _load_service_by_id(db, business_id, sid)


def _format_slot_menu(slots: list[Slot]) -> str:
    return "\n".join(f"- {s.display}" for s in slots)


async def _handle_awaiting_date(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> dict:
    """Parse the customer's date, validate, find slots, advance to awaiting_slot.

    Failure modes (each results in an explanatory reply, draft stays at
    awaiting_date so customer can retry):
    - No date detectable in the message
    - Date in the past
    - Date beyond business.booking_window_days
    - Business closed that day
    - No available slots after conflicts/filters

    On success: draft.requested_date / time_window / offered_slots are saved,
    stage advances to awaiting_slot, and the slots are presented.
    """
    business = await _load_business(state.db, state.business_id)
    if business is None:
        logger.warning("_handle_awaiting_date: business %s not found", state.business_id)
        return {
            "assistant_message": (
                "I'm having trouble accessing the booking system. "
                "Please try again in a moment."
            )
        }

    service = await _load_service(state.db, state.business_id, draft.get("service_id", ""))
    if service is None:
        # Service was deleted/deactivated since draft started — reset.
        draft.clear()
        await _save_booking_draft(state.db, conversation, draft)
        return {
            "assistant_message": (
                "The service you picked is no longer available. "
                "Could you let me know what you'd like to book instead?"
            )
        }

    parsed_date = await parse_booking_date(
        state.user_message,
        business_timezone=business.timezone,
    )

    if parsed_date is None:
        return {
            "assistant_message": (
                "I didn't catch a date there. Could you tell me a day that "
                "works for you? For example: 'next Saturday' or 'June 7'."
            )
        }

    today = today_in_business_tz(business.timezone)

    if parsed_date < today:
        return {
            "assistant_message": (
                f"That date ({parsed_date.strftime('%A, %B %d')}) is already in "
                "the past. What upcoming date works?"
            )
        }

    from datetime import timedelta as _td  # local; avoids top-level clutter

    max_date = today + _td(days=business.booking_window_days)
    if parsed_date > max_date:
        return {
            "assistant_message": (
                f"We can only book up to {business.booking_window_days} days "
                f"ahead — so the latest is {max_date.strftime('%A, %B %d')}. "
                "Could you choose a closer date?"
            )
        }

    time_window = extract_time_window(state.user_message)

    slots = await find_available_slots(
        state.db,
        business=business,
        service=service,
        target_date=parsed_date,
        time_window=time_window,
        limit=3,
    )

    if not slots:
        # Could be: closed that day, fully booked, or window has no openings.
        # Distinguish closed-day case for a more helpful message.
        from app.services.slot_finder import _get_operating_hours, weekday_string

        hours = await _get_operating_hours(
            state.db, business.id, weekday_string(parsed_date)
        )
        if hours is None or hours.is_closed:
            return {
                "assistant_message": (
                    f"We're closed on {parsed_date.strftime('%A')}. "
                    "What other date works for you?"
                )
            }
        if time_window:
            return {
                "assistant_message": (
                    f"I don't see {time_window} openings on "
                    f"{parsed_date.strftime('%A, %B %d')}. Would another day "
                    "or a different time of day work?"
                )
            }
        return {
            "assistant_message": (
                f"Unfortunately {parsed_date.strftime('%A, %B %d')} is fully "
                "booked. Could you try another date?"
            )
        }

    # Persist
    draft["requested_date"] = parsed_date.isoformat()
    draft["time_window"] = time_window
    draft["offered_slots"] = [s.iso for s in slots]
    draft["stage"] = STAGE_AWAITING_SLOT
    await _save_booking_draft(state.db, conversation, draft)

    logger.info(
        "booking_node: advanced to awaiting_slot — date=%s window=%r slots=%d",
        parsed_date,
        time_window,
        len(slots),
    )

    menu = _format_slot_menu(slots)
    return {
        "assistant_message": (
            f"Great — here's what's available on "
            f"{parsed_date.strftime('%A, %B %d')}:\n\n{menu}\n\n"
            "Which time works for you?"
        )
    }


# ---------------------------------------------------------------------------
# Slot stage
# ---------------------------------------------------------------------------

_SLOT_MATCH_PROMPT = """The customer was offered these time slots:
{options}

Which slot did the customer pick? Output ONLY the slot number (one digit) or \
the word NONE if unclear.

Rules:
- "first" / "first one" / "1st" → 1
- "second" / "middle" / "2nd" → 2
- "third" / "last" / "3rd" → 3 (only if 3 slots exist)
- A specific time (e.g. "10:30 AM", "10:30", "10:30am", "the 10:30") matches \
that slot by time
- "any" / "any one" / "you pick" / "whatever" → 1 (first available)
- "yes" / "ok" / "sure" / "sounds good" → 1
- If the customer named something not in the list or is genuinely unclear, \
output NONE

Output ONLY a single digit (1-N) or NONE. No explanation, no punctuation."""


_SLOT_NUMBER_RE = re.compile(r"\b([1-9])\b")


def _format_slot_choices(slots: list[datetime]) -> str:
    """Numbered list of slot times for the LLM matcher prompt."""
    return "\n".join(
        f"{i + 1}. {dt.strftime('%I:%M %p').lstrip('0')}"
        for i, dt in enumerate(slots)
    )


def _format_slot_menu_from_iso(offered_iso: list[str]) -> str:
    """Bullet menu used when re-presenting slots to the customer on no-match."""
    lines: list[str] = []
    for iso in offered_iso:
        try:
            dt = datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            continue
        lines.append(f"- {dt.strftime('%I:%M %p').lstrip('0')}")
    return "\n".join(lines)


async def _match_slot_choice(
    user_message: str, offered: list[datetime]
) -> datetime | None:
    """Use the LLM to map the customer's text to one of the offered slots.

    Returns the matched datetime, or None if the matcher couldn't confidently
    pick. The fast model is fine here — selection among 1-3 enumerated options
    is a simpler task than free-form date parsing.
    """
    if not offered:
        return None

    prompt = _SLOT_MATCH_PROMPT.format(options=_format_slot_choices(offered))

    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            model=settings.GROQ_MODEL_FAST,
            temperature=0.0,
            max_tokens=10,
        )
    except LLMError as exc:
        logger.warning("Slot matcher LLM call failed: %s", exc)
        return None

    cleaned = raw.strip().rstrip(".").strip("'\"")
    if cleaned.upper() == "NONE":
        logger.info("Slot matcher: NONE from LLM for %r", user_message[:40])
        return None

    match = _SLOT_NUMBER_RE.search(cleaned)
    if not match:
        logger.info("Slot matcher: no digit in LLM output %r", raw[:40])
        return None

    idx = int(match.group(1)) - 1
    if idx < 0 or idx >= len(offered):
        logger.info(
            "Slot matcher: index %d out of range (%d offered)", idx, len(offered)
        )
        return None

    chosen = offered[idx]
    logger.info(
        "Slot matcher: %r → slot %d (%s)", user_message[:40], idx + 1, chosen
    )
    return chosen


async def _handle_awaiting_slot(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> dict:
    """Match the customer's pick to a previously-offered slot.

    On success: write slot_start_at to draft, advance to awaiting_contact.
    On match failure: re-present the slot menu.
    On state corruption (draft has no offered_slots, or they fail to parse):
    reset to awaiting_date so the customer can pick a date again.
    """
    offered_iso = draft.get("offered_slots") or []

    if not offered_iso:
        logger.warning(
            "_handle_awaiting_slot: no offered_slots in draft — resetting to awaiting_date"
        )
        draft["stage"] = STAGE_AWAITING_DATE
        draft.pop("requested_date", None)
        draft.pop("time_window", None)
        await _save_booking_draft(state.db, conversation, draft)
        return {
            "assistant_message": (
                "Something went sideways on my end with the time options. "
                "What date would you like to book for?"
            )
        }

    try:
        offered = [datetime.fromisoformat(iso) for iso in offered_iso]
    except (TypeError, ValueError):
        logger.warning(
            "_handle_awaiting_slot: bad offered_slots in draft: %r", offered_iso
        )
        draft["stage"] = STAGE_AWAITING_DATE
        draft.pop("offered_slots", None)
        await _save_booking_draft(state.db, conversation, draft)
        return {
            "assistant_message": (
                "Something went sideways on my end with the time options. "
                "What date would you like to book for?"
            )
        }

    chosen = await _match_slot_choice(state.user_message, offered)

    if chosen is None:
        menu = _format_slot_menu_from_iso(offered_iso)
        return {
            "assistant_message": (
                "I didn't catch which time you wanted. Could you tell me which "
                f"works?\n\n{menu}"
            )
        }

    # Persist the chosen slot and advance the draft.
    draft["slot_start_at"] = chosen.isoformat()
    draft["stage"] = STAGE_AWAITING_CONTACT
    await _save_booking_draft(state.db, conversation, draft)

    date_str = chosen.strftime("%A, %B %d")
    time_str = chosen.strftime("%I:%M %p").lstrip("0")
    logger.info(
        "booking_node: slot selected — %s at %s", date_str, time_str
    )
    return {
        "assistant_message": (
            f"Got it — {date_str} at {time_str}. To confirm the booking I "
            "just need a few details. What's your full name?"
        )
    }


# ---------------------------------------------------------------------------
# Contact stage
# ---------------------------------------------------------------------------

# Email regex: pragmatic, not RFC-perfect. We just want to know whether the
# message contains something email-shaped. We do not validate the domain.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Minimum number of digits a "phone number" must contain. Bangladesh local
# numbers are 11 digits; international format is up to 15. Allow as low as 7
# for international short codes / partial numbers (we'll still capture them
# without rejecting an otherwise valid customer entry).
_PHONE_MIN_DIGITS = 7
_PHONE_MAX_DIGITS = 15


# Common preambles to strip from the start of a message before treating
# the rest as the customer's name. Greedy: longer phrases first so that
# "hi i'm John" strips both "hi" and "i'm" rather than just "hi".
_NAME_PREAMBLE_RE = re.compile(
    r"^("
    r"(?:hi|hello|hey),?\s+(?:i'?m|i\s+am|this\s+is)\s+|"
    r"my\s+name\s+is\s+|"
    r"this\s+is\s+|"
    r"call\s+me\s+|"
    r"i\s+am\s+|"
    r"i'?m\s+|"
    r"it'?s\s+|"
    r"name'?s\s+"
    r")",
    re.IGNORECASE,
)

# Words that strongly suggest the message is a booking-related sentence
# rather than a name. Checked as whole words (\b) so we don't false-reject
# real names that happen to contain these substrings (e.g. "Booker" in a
# surname). Greetings included so "hi there John" doesn't sneak past the
# preamble strip and get captured wholesale.
_NAME_REJECT_WORD_RE = re.compile(
    r"\b(?:book|booking|schedule|scheduling|appointment|appointments|"
    r"want|wants|wanted|need|needs|needed|would|could|should|"
    r"cancel|cancels|cancelled|reschedule|rescheduling|"
    r"reserve|reserves|reserved|"
    r"hi|hello|hey|thanks|thank)\b",
    re.IGNORECASE,
)


def _extract_name(message: str) -> str | None:
    """Pull a plausible full name out of the customer's message.

    Strips a leading preamble ("my name is X", "I'm X", "Hi, I'm X") so
    the bot doesn't capture those framing words as part of the name.

    Then validates: 2-100 chars, at least one letter, at most 6 words,
    no booking-request verbs. The word-count + verb checks catch the
    common failure mode where a customer starts over mid-flow ("I want
    to book a routine cleaning") at the awaiting_contact stage and the
    handler would otherwise treat that sentence as their name.

    Lenient on cultural variation: single-word names (Madonna, Cher) are
    valid, and 6 words covers long honorifics like "Sheikh Mohammed bin
    Rashid Al Maktoum" without being so loose that "I want to book a
    routine cleaning" gets through.

    Returns the cleaned name, or None if the message doesn't look like a
    name. In the None case the caller re-asks the same field.
    """
    raw = message.strip()
    if not raw:
        return None

    # Strip a leading preamble like "my name is", "I'm", "hi I am", etc.
    name = _NAME_PREAMBLE_RE.sub("", raw, count=1).strip()
    name = name.rstrip(".!,;:")  # drop trailing punctuation

    if len(name) < 2 or len(name) > 100:
        return None
    if not any(c.isalpha() for c in name):
        return None

    # Reject obvious non-names.
    if len(name.split()) > 6:
        return None
    if _NAME_REJECT_WORD_RE.search(name):
        return None

    return name


def _extract_email(message: str) -> str | None:
    """Find the first email-shaped substring in the message, lowercased."""
    match = _EMAIL_RE.search(message)
    if not match:
        return None
    return match.group(0).lower()


def _extract_phone(message: str) -> str | None:
    """Return a normalized phone string if the message contains enough digits.

    Strips everything except digits and a leading '+'. Counts digits; if the
    count is in the plausible range, returns the cleaned form. Otherwise None.
    """
    # Keep digits and + only
    cleaned = re.sub(r"[^\d+]", "", message)
    # The '+' is only valid as the first char
    if cleaned.startswith("+"):
        digits = cleaned[1:]
    else:
        digits = cleaned
    if not digits.isdigit():
        return None
    if not (_PHONE_MIN_DIGITS <= len(digits) <= _PHONE_MAX_DIGITS):
        return None
    return cleaned


async def _handle_awaiting_contact(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> dict:
    """Walk the customer through name → email → phone collection.

    Routes by inspecting which fields are already in the draft:
    - customer_name missing → this turn IS the name. Save, ask for email.
    - customer_email missing → this turn IS the email. Save, ask for phone.
    - customer_phone missing → this turn IS the phone. Save, advance to
      STAGE_COMPLETE.

    On unparseable input, re-asks for the same field without advancing.

    (Booking row creation happens in 4.6.4 — for now we just persist the
    contact fields in the draft and stop with an acknowledgement.)
    """
    # --- Collecting the name --------------------------------------------------
    if draft.get("customer_name") is None:
        name = _extract_name(state.user_message)
        if name is None:
            return {
                "assistant_message": (
                    "I didn't quite catch your name. Could you tell me your "
                    "full name?"
                )
            }
        draft["customer_name"] = name
        # Stage stays at AWAITING_CONTACT — we're still in the contact sub-flow.
        await _save_booking_draft(state.db, conversation, draft)
        logger.info("booking_node: contact name captured")
        first = name.split()[0]
        return {
            "assistant_message": (
                f"Thanks, {first}. What's your email address?"
            )
        }

    # --- Collecting the email -------------------------------------------------
    if draft.get("customer_email") is None:
        email = _extract_email(state.user_message)
        if email is None:
            return {
                "assistant_message": (
                    "That doesn't look like a valid email address. Could you "
                    "double-check and send it again?"
                )
            }
        draft["customer_email"] = email
        await _save_booking_draft(state.db, conversation, draft)
        logger.info("booking_node: contact email captured")
        return {
            "assistant_message": (
                "Got it. And what's the best phone number to reach you on?"
            )
        }

    # --- Collecting the phone -------------------------------------------------
    if draft.get("customer_phone") is None:
        phone = _extract_phone(state.user_message)
        if phone is None:
            return {
                "assistant_message": (
                    "That doesn't look like a valid phone number. Could you "
                    "send it again? Country code is fine."
                )
            }
        draft["customer_phone"] = phone

        # Create the actual Booking row (and update Customer) BEFORE we
        # advance the stage. If _finalize_booking raises, draft is still
        # at AWAITING_CONTACT with all three contact fields filled — on
        # retry, the warning branch at the bottom of this function picks
        # it up. Better than a half-finished state where stage=COMPLETE
        # but no Booking row exists.
        try:
            booking, when_str = await _finalize_booking(
                state, conversation, draft
            )
        except Exception:
            logger.exception("booking_node: _finalize_booking failed")
            return {
                "assistant_message": (
                    "Hmm — I ran into a snag finalizing your booking just "
                    "now. Could you try once more? If it keeps happening, "
                    f"please reach out to {state.business_name} directly."
                )
            }

        # Booking persisted successfully — now advance the stage.
        draft["stage"] = STAGE_COMPLETE
        await _save_booking_draft(state.db, conversation, draft)
        logger.info(
            "booking_node: booking %s created, advanced draft to COMPLETE",
            booking.id,
        )

        return {
            "assistant_message": (
                f"You're all set! I've booked your "
                f"{draft.get('service_name', 'appointment')} for {when_str}. "
                f"The {state.business_name} team will reach out shortly to "
                "confirm. Anything else I can help with?"
            )
        }

    # All fields filled but stage is still AWAITING_CONTACT — shouldn't reach
    # here in normal flow. Advance to COMPLETE defensively.
    draft["stage"] = STAGE_COMPLETE
    await _save_booking_draft(state.db, conversation, draft)
    logger.warning(
        "booking_node: awaiting_contact reached with all fields already set — advancing to COMPLETE"
    )
    return {
        "assistant_message": (
            f"Thanks! The {state.business_name} team will follow up to confirm. "
            "Anything else I can help with?"
        )
    }


# ---------------------------------------------------------------------------
# Booking creation (4.6.4)
# ---------------------------------------------------------------------------


async def _finalize_booking(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> tuple[Booking, str]:
    """Create the Booking row, update Customer with real contact info, link
    the booking to the conversation.

    Idempotent via ``Booking.idempotency_key = f"chat:{conversation.id}"``.
    Safe to call multiple times for the same conversation: a second call
    returns the existing booking rather than violating the UNIQUE constraint.
    Caller MUST have populated draft with customer_name, customer_email,
    customer_phone, service_id, and slot_start_at.

    Returns (booking, when_str) where when_str is the booking time in the
    business's local timezone, formatted for the customer-facing reply.
    """
    # Fetch business (needed for timezone + currency).
    bus_result = await state.db.execute(
        select(Business).where(Business.id == conversation.business_id)
    )
    business = bus_result.scalar_one()

    # Fetch service (needed for duration + price).
    service_id = UUID(draft["service_id"])
    svc_result = await state.db.execute(
        select(Service).where(Service.id == service_id)
    )
    service = svc_result.scalar_one()

    # Fetch customer (we'll update its contact info).
    cust_result = await state.db.execute(
        select(Customer).where(Customer.id == conversation.customer_id)
    )
    customer = cust_result.scalar_one()

    # Update customer with real contact info. The placeholder row created
    # on the first chat turn carried anonymous values; we replace them
    # with what the customer told us. Assigning the same values twice is
    # a no-op as far as SQLAlchemy is concerned, so this is safe on retry.
    customer.full_name = draft["customer_name"]
    customer.email = draft["customer_email"]
    customer.phone = draft["customer_phone"]

    # Convert the slot's naive local datetime to UTC TIMESTAMPTZ for storage.
    # slot_start_at was computed in slot_finder using business-local times
    # and serialized as a naive ISO string. We re-attach the business
    # timezone and convert to UTC for the timezone-aware DateTime column.
    slot_local_naive = datetime.fromisoformat(draft["slot_start_at"])
    try:
        business_tz = ZoneInfo(business.timezone)
    except Exception:
        logger.warning(
            "Unknown business timezone %r — falling back to UTC", business.timezone
        )
        business_tz = ZoneInfo("UTC")
    slot_local_aware = slot_local_naive.replace(tzinfo=business_tz)
    starts_at_utc = slot_local_aware.astimezone(ZoneInfo("UTC"))
    ends_at_utc = starts_at_utc + timedelta(minutes=service.duration_minutes)

    # Idempotency: one chat conversation can produce at most one booking.
    # If a booking with this key already exists (a retry after partial
    # failure, or a duplicate submit from the client), reuse it rather
    # than violating the UNIQUE constraint.
    idempotency_key = f"chat:{conversation.id}"
    existing_result = await state.db.execute(
        select(Booking).where(Booking.idempotency_key == idempotency_key)
    )
    booking = existing_result.scalar_one_or_none()

    if booking is None:
        booking = Booking(
            business_id=conversation.business_id,
            customer_id=customer.id,
            service_id=service.id,
            conversation_id=conversation.id,
            starts_at=starts_at_utc,
            ends_at=ends_at_utc,
            status=BookingStatus.PENDING_PAYMENT,
            total_amount=service.price if service.price is not None else Decimal("0.00"),
            currency=business.currency,
            idempotency_key=idempotency_key,
        )
        state.db.add(booking)
        await state.db.flush()
        logger.info(
            "booking_node: created Booking id=%s starts_at=%s service=%r customer=%r",
            booking.id, starts_at_utc.isoformat(), service.name, customer.full_name,
        )
    else:
        logger.info(
            "booking_node: reusing existing Booking id=%s for idempotency_key=%s",
            booking.id, idempotency_key,
        )

    # Human-readable time in business local timezone for the reply.
    when_str = (
        f"{slot_local_aware.strftime('%A, %B %d')} at "
        f"{slot_local_aware.strftime('%I:%M %p').lstrip('0')}"
    )

    return booking, when_str
