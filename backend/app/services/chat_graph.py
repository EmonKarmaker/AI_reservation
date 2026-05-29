"""LangGraph chat receptionist (Phase 4.5 — intent-routed).

Graph layout:

    load_history → classify_intent → [router] → one of:
        question  → retrieve → answer
        booking   → booking_stub
        escalate  → escalate_stub
    → save_turn → END

Multi-tenancy: business_id is REQUIRED in state. retrieve_relevant filters
by it and the system prompt tells the LLM to ground on the provided context
only.

Async end-to-end (Groq + pgvector are async-only). Compiled graph is a
module-level singleton; only per-request state is fresh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.integrations.llm import chat_completion
from app.integrations.resend_email import EmailError, send_email
from app.models.business_setting import BusinessSetting
from app.models.enums import MessageRole
from app.models.message import Message
from app.services.conversation_store import (
    append_message,
    get_or_create_conversation,
    list_recent_messages,
)
from app.services.rag import RetrievedChunk, retrieve_relevant


logger = logging.getLogger(__name__)


# Intent labels. Stable, short. Adding more later means updating: (a) the
# classifier prompt, (b) _parse_intent, (c) _route_by_intent.
Intent = Literal["question", "booking", "escalate"]
INTENT_VALUES: tuple[Intent, ...] = ("question", "booking", "escalate")
DEFAULT_INTENT: Intent = "question"


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

@dataclass
class ChatState:
    """State carried across all graph nodes.

    Required inputs:
    - db, business_id, business_name, customer_id, user_message

    Optional inputs:
    - business_greeting, business_personality

    Filled by nodes:
    - conversation_id (load_history)
    - history (load_history)
    - intent (classify_intent)
    - retrieved_chunks (retrieve, question branch only)
    - assistant_message (answer / booking_stub / escalate_stub)
    """

    # Required inputs
    db: AsyncSession
    business_id: UUID
    business_name: str
    customer_id: UUID
    user_message: str

    # Optional inputs
    business_greeting: str | None = None
    business_personality: str | None = None

    # Filled by nodes
    conversation_id: UUID | None = None
    history: list[Message] = field(default_factory=list)
    intent: Intent = DEFAULT_INTENT
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    assistant_message: str = ""


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def load_history_node(state: ChatState) -> dict:
    """Resolve the conversation and load the last N messages."""
    conversation = await get_or_create_conversation(
        state.db,
        business_id=state.business_id,
        customer_id=state.customer_id,
    )
    history = await list_recent_messages(
        state.db,
        conversation_id=conversation.id,
    )
    logger.info(
        "Loaded conversation=%s with %d prior messages",
        conversation.id,
        len(history),
    )
    return {"conversation_id": conversation.id, "history": history}


# --- Intent classification -------------------------------------------------

_INTENT_SYSTEM_PROMPT = """You classify the customer's MOST RECENT message in \
a chat with an AI receptionist for a small business.

Output EXACTLY one word, one of: question, booking, escalate

Definitions:
- booking   -> the customer wants to BOOK, RESERVE, SCHEDULE, CANCEL, or \
RESCHEDULE an appointment. Verbs like "book", "schedule", "reserve", "make an \
appointment", "set up", or any confirmation like "yes" or "sure" after the AI \
offered to schedule something.
- escalate  -> the customer is angry, frustrated, demanding a manager/human, \
making a complaint, or describing an emergency.
- question  -> EVERYTHING ELSE. Asking about prices, services, hours, \
policies, locations, or any informational query.

Examples:

Customer: "How much does a cleaning cost?"
Label: question

Customer: "Can I book an appointment for Saturday?"
Label: booking

Customer: "I'd like to schedule a checkup."
Label: booking

Customer: "Great, can I book one for Saturday morning?"
Label: booking

Customer: "Yes, please book it."
Label: booking

Customer: "What time do you close?"
Label: question

Customer: "Do you take walk-ins?"
Label: question

Customer: "I want to cancel my appointment."
Label: booking

Customer: "This is ridiculous, I want a manager!"
Label: escalate

Customer: "I've been waiting 30 minutes, this is unacceptable."
Label: escalate

Respond with the single label word only. No explanation, no punctuation."""


def _parse_intent(raw: str) -> Intent:
    """Parse LLM output into a known Intent label. Falls back to DEFAULT_INTENT."""
    candidate = raw.strip().lower().rstrip(".").strip("'\"")
    if candidate not in INTENT_VALUES:
        first = candidate.split()[0] if candidate else ""
        candidate = first
    if candidate in INTENT_VALUES:
        return candidate  # type: ignore[return-value]
    return DEFAULT_INTENT


async def classify_intent_node(state: ChatState) -> dict:
    """Classify the customer's intent using the fast Groq model."""
    from app.config import settings

    messages: list[dict] = [{"role": "system", "content": _INTENT_SYSTEM_PROMPT}]

    # Include up to last 4 prior turns for context. Enough to disambiguate
    # "yes" or "sure" without drowning out the current message.
    for m in state.history[-4:]:
        if m.role in (MessageRole.USER, MessageRole.ASSISTANT):
            messages.append({"role": m.role.value, "content": m.content})

    messages.append({"role": "user", "content": state.user_message})

    try:
        raw = await chat_completion(
            messages,
            model=settings.GROQ_MODEL_SMART,
            temperature=0.0,
            max_tokens=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Intent classifier failed: %s — defaulting to %s", exc, DEFAULT_INTENT)
        return {"intent": DEFAULT_INTENT}

    intent = _parse_intent(raw)
    logger.info("Classified intent: %s (raw=%r)", intent, raw[:30])
    return {"intent": intent}


# --- Retrieval (question branch) -------------------------------------------

async def retrieve_node(state: ChatState) -> dict:
    """Retrieve top-k relevant embeddings for the user's message."""
    chunks = await retrieve_relevant(
        state.db,
        business_id=state.business_id,
        query=state.user_message,
        top_k=5,
    )
    logger.info(
        "RAG retrieved %d chunks for business=%s, query=%r",
        len(chunks),
        state.business_id,
        state.user_message[:60],
    )
    return {"retrieved_chunks": chunks}


# --- Answer (question branch) ----------------------------------------------

def _build_system_prompt(state: ChatState) -> str:
    """Compose system prompt with business identity + personality + RAG context."""
    parts: list[str] = []

    parts.append(
        f"You are the AI receptionist for {state.business_name}. "
        "Answer the customer's question concisely, in a friendly and "
        "professional tone."
    )

    if state.business_personality:
        parts.append(f"Personality / style guide: {state.business_personality}")

    parts.append(
        "IMPORTANT: Only answer using the CONTEXT below. If the context "
        "does not contain enough information to answer, say so honestly and "
        "offer to connect them with a human team member. Never invent "
        "prices, services, hours, or policies."
    )

    if state.retrieved_chunks:
        context_lines = [
            f"- [{c.source_type.value}] {c.content}" for c in state.retrieved_chunks
        ]
        parts.append("CONTEXT:\n" + "\n".join(context_lines))
    else:
        parts.append(
            "CONTEXT: (none available — tell the customer you don't have "
            "that information on hand and suggest reaching out directly.)"
        )

    return "\n\n".join(parts)


async def answer_node(state: ChatState) -> dict:
    """Call the LLM with system prompt + history + new user message."""
    system_prompt = _build_system_prompt(state)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Replay prior turns. Filter out non-user/assistant roles — the OpenAI
    # schema rejects unknown ones, and there's no point forwarding tool/system
    # messages from earlier turns to a fresh prompt.
    for m in state.history:
        if m.role in (MessageRole.USER, MessageRole.ASSISTANT):
            messages.append({"role": m.role.value, "content": m.content})

    messages.append({"role": "user", "content": state.user_message})

    try:
        reply = await chat_completion(messages, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed in answer_node: %s", exc)
        reply = (
            "I'm having trouble answering that right now. Could you try again "
            "in a moment, or contact us directly?"
        )

    return {"assistant_message": reply}


# --- Booking + escalate stubs (replaced in Phase 4.6/4.8) -----------------

async def booking_stub_node(state: ChatState) -> dict:
    """Polite deferral for booking requests. Phase 4.6 replaces this."""
    reply = (
        f"I'd love to help you book that. Let me hand you to the {state.business_name} "
        "team — they'll reach out to confirm the details. In the meantime, can I "
        "answer any other questions?"
    )
    return {"assistant_message": reply}


def _format_escalation_email(state: ChatState) -> tuple[str, str]:
    """Compose (subject, html) for the escalation email.

    Includes the triggering message, the customer_id, and the last 6 turns
    of conversation so the human responder has context.
    """
    subject = f"[Chat escalation] {state.business_name} — customer needs help"

    # Render last 6 turns as a simple HTML transcript.
    transcript_rows: list[str] = []
    for m in state.history[-6:]:
        role_label = m.role.value if hasattr(m.role, "value") else str(m.role)
        # Light XSS guard: replace angle brackets. The recipient is the
        # business owner so the risk is low, but emails get forwarded,
        # archived, sometimes rendered in surprising places.
        safe_content = (
            m.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        transcript_rows.append(
            f"<p><strong>{role_label.title()}:</strong> {safe_content}</p>"
        )
    transcript_html = "\n".join(transcript_rows) if transcript_rows else (
        "<p><em>(no prior messages)</em></p>"
    )

    triggering = (
        state.user_message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    html = f"""\
<h2>A customer needs human help</h2>

<p>The AI receptionist for <strong>{state.business_name}</strong> escalated
the following conversation. The customer is anonymous (web chat); use the
customer_id below if you need to look them up.</p>

<h3>Triggering message</h3>
<blockquote>{triggering}</blockquote>

<h3>Recent conversation</h3>
{transcript_html}

<hr/>
<p style="color:#666;font-size:12px">
customer_id: {state.customer_id}<br/>
conversation_id: {state.conversation_id}
</p>
"""
    return subject, html


async def _fetch_escalation_email(state: ChatState) -> str | None:
    """Look up the business's configured escalation email. None if not set."""
    result = await state.db.execute(
        select(BusinessSetting.escalation_email).where(
            BusinessSetting.business_id == state.business_id
        )
    )
    row = result.scalar_one_or_none()
    # CITEXT column may return None or the empty string; normalise both.
    if row:
        stripped = row.strip()
        if stripped:
            return stripped
    return None


async def escalate_stub_node(state: ChatState) -> dict:
    """Acknowledge an escalation request and send a notification email.

    Best-effort: any failure (no escalation_email configured, Resend down,
    network failure) is logged but does NOT break the chat reply. The
    customer always gets an acknowledgment.

    Phase 4.8: real email via Resend. The recipient is the business's
    ``business_settings.escalation_email``.
    """
    logger.info(
        "Escalation triggered for business=%s, customer=%s, message=%r",
        state.business_id,
        state.customer_id,
        state.user_message[:80],
    )

    # Best-effort: fetch the configured escalation_email + send. Catches
    # everything — the chatbot reply must NOT depend on the email landing.
    try:
        recipient = await _fetch_escalation_email(state)
        if recipient is None:
            logger.info(
                "No escalation_email configured for business=%s; skipping send",
                state.business_id,
            )
        else:
            subject, html = _format_escalation_email(state)
            message_id = await send_email(to=recipient, subject=subject, html=html)
            logger.info(
                "Escalation email sent to %s (resend message_id=%s) for business=%s",
                recipient,
                message_id,
                state.business_id,
            )
    except EmailError as exc:
        logger.warning(
            "Failed to send escalation email for business=%s: %s",
            state.business_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001 — defensive: never break the chat
        logger.warning(
            "Unexpected error in escalation flow for business=%s: %s",
            state.business_id,
            exc,
        )

    reply = (
        f"I understand — let me get a human from the {state.business_name} team "
        "involved right away. They'll be in touch shortly. Is there anything "
        "urgent I should pass along?"
    )
    return {"assistant_message": reply}


# --- Persistence (all branches) --------------------------------------------

async def save_turn_node(state: ChatState) -> dict:
    """Persist the user message and the AI reply.

    Best-effort: a failure here doesn't poison the in-memory state. Caller
    still gets a usable assistant_message; the conversation just won't be
    re-readable later if persistence broke.
    """
    if state.conversation_id is None:
        logger.warning("save_turn_node: no conversation_id; skipping persistence")
        return {}

    try:
        await append_message(
            state.db,
            conversation_id=state.conversation_id,
            role=MessageRole.USER,
            content=state.user_message,
        )
        await append_message(
            state.db,
            conversation_id=state.conversation_id,
            role=MessageRole.ASSISTANT,
            content=state.assistant_message,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to persist chat turn: %s", exc)

    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _route_by_intent(state: ChatState) -> str:
    """Map intent → next node name for the conditional edge."""
    if state.intent == "booking":
        return "booking_stub"
    if state.intent == "escalate":
        return "escalate_stub"
    return "retrieve"


def build_chat_graph():
    """Construct the intent-routed chat graph."""
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ChatState)

    graph.add_node("load_history", load_history_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("answer", answer_node)
    graph.add_node("booking_stub", booking_stub_node)
    graph.add_node("escalate_stub", escalate_stub_node)
    graph.add_node("save_turn", save_turn_node)

    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "retrieve": "retrieve",
            "booking_stub": "booking_stub",
            "escalate_stub": "escalate_stub",
        },
    )

    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", "save_turn")
    graph.add_edge("booking_stub", "save_turn")
    graph.add_edge("escalate_stub", "save_turn")
    graph.add_edge("save_turn", END)

    return graph.compile()


_compiled_graph = None


def get_chat_graph():
    """Lazy singleton accessor for the compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_chat_graph()
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def run_chat_turn(
    *,
    db: AsyncSession,
    business_id: UUID,
    business_name: str,
    customer_id: UUID,
    user_message: str,
    business_greeting: str | None = None,
    business_personality: str | None = None,
) -> ChatState:
    """Run one user message through the graph and return the final state."""
    graph = get_chat_graph()

    initial_state = ChatState(
        db=db,
        business_id=business_id,
        business_name=business_name,
        customer_id=customer_id,
        user_message=user_message,
        business_greeting=business_greeting,
        business_personality=business_personality,
    )

    result = await graph.ainvoke(initial_state)
    if isinstance(result, ChatState):
        return result

    return ChatState(
        db=db,
        business_id=business_id,
        business_name=business_name,
        customer_id=customer_id,
        user_message=user_message,
        business_greeting=business_greeting,
        business_personality=business_personality,
        conversation_id=result.get("conversation_id"),
        history=result.get("history", []),
        intent=result.get("intent", DEFAULT_INTENT),
        retrieved_chunks=result.get("retrieved_chunks", []),
        assistant_message=result.get("assistant_message", ""),
    )
