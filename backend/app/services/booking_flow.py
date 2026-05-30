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
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business
from app.models.conversation import Conversation
from app.models.enums import EmbeddingSourceType
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
    """Return the booking_draft sub-dict from langgraph_state. Empty if none.

    Defensive: langgraph_state has a JSONB server_default of '{}', but for
    older conversations or weird states it could theoretically be None.
    """
    state = conversation.langgraph_state or {}
    draft = state.get("booking_draft")
    if not isinstance(draft, dict):
        draft = {}
    return draft


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

    # STAGE_AWAITING_SLOT, _CONTACT, and _COMPLETE will be implemented in
    # later sub-phases (4.6.2b through 4.6.4). Polite acknowledgment for now.
    return {
        "assistant_message": (
            f"Got it — I've noted that. The next part of the booking flow is "
            f"still being set up, so a team member from {state.business_name} "
            "will follow up shortly to confirm. Anything else I can help with?"
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
