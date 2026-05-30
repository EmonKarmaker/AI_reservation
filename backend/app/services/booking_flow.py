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

from app.models.conversation import Conversation
from app.models.enums import EmbeddingSourceType
from app.models.service import Service
from app.services.rag import retrieve_relevant

if TYPE_CHECKING:
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


async def _save_booking_draft(
    db: AsyncSession,
    conversation: Conversation,
    draft: dict,
) -> None:
    """Persist booking_draft back into conversations.langgraph_state.

    We REPLACE the whole top-level dict (rather than mutating in place) so
    SQLAlchemy's change-detection sees the update. In-place mutation of
    JSONB columns is famously not detected without sqlalchemy.ext.mutable.

    Only the booking_draft sub-key is touched; other state keys are
    preserved.
    """
    state = dict(conversation.langgraph_state or {})
    state["booking_draft"] = draft
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

    # Phases 4.6.2+ will fill these in. For now, polite placeholder that
    # acknowledges progress without pretending to handle the step.
    return {
        "assistant_message": (
            f"Got it — I've noted that. The full booking flow is still being "
            f"set up, so a team member from {state.business_name} will follow "
            "up shortly to confirm the date and time. Anything else I can help with?"
        )
    }


async def _handle_awaiting_service(
    state: "ChatState",
    conversation: Conversation,
    draft: dict,
) -> dict:
    """Identify the requested service or ask the customer to pick one."""
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
