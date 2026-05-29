"""Minimal LangGraph chat receptionist (Phase 4.3 — 3 nodes only).

This is the foundation. Phase 4.5+ will expand this graph with intent
classification, booking flow, and escalation. For now we deliver the
simplest viable Q&A bot:

    entry → retrieve → answer → END

State carries the user's message, the retrieved RAG chunks, and the
assistant's reply. The graph is async end-to-end (Groq + pgvector are both
async-only) and returns a complete final state on each invocation.

Multi-tenancy: business_id is REQUIRED in state. retrieve_relevant filters by
it, and the system prompt explicitly tells the LLM to only answer based on
the provided context. There is no path through this graph that lets the
chatbot see another tenant's data.

Why we use a graph at all for 3 nodes: it's the foundation. Phase 4.5
introduces a router node that branches between question-answering and the
booking flow, and that's exactly the kind of thing LangGraph is for. Building
it as a graph from day one keeps the API stable across phases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm import chat_completion
from app.models.enums import MessageRole
from app.models.message import Message
from app.services.conversation_store import (
    append_message,
    get_or_create_conversation,
    list_recent_messages,
)
from app.services.rag import RetrievedChunk, retrieve_relevant


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

@dataclass
class ChatState:
    """State carried across all graph nodes.

    Required inputs:
    - ``db``           : Active async session.
    - ``business_id``  : Tenant whose embeddings to search.
    - ``business_name``: Used in the system prompt.
    - ``customer_id``  : Identifies the chat session. The frontend generates
                         this per-browser; for now any stable UUID works.
    - ``user_message`` : The customer's latest message.

    Optional inputs:
    - ``business_greeting``    : The business's configured AI greeting.
    - ``business_personality`` : The business's configured AI personality.

    Populated by graph execution:
    - ``conversation_id``  : The conversation row id (loaded by 'load_history').
    - ``history``          : Prior messages, oldest first (loaded by 'load_history').
    - ``retrieved_chunks`` : RAG results (loaded by 'retrieve').
    - ``assistant_message``: Final LLM reply (loaded by 'answer').
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


def _build_system_prompt(state: ChatState) -> str:
    """Compose the system prompt with business info + retrieved context.

    The system prompt does three things:
    1. Sets identity (the AI works for this specific business).
    2. Encodes the business's configured personality + greeting style.
    3. Provides the retrieved chunks as ground truth, with explicit
       instructions not to fabricate beyond them.

    This is the most important prompt in the whole system. Phase 4.5+ will
    extend it but the spine stays the same.
    """
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

    # Replay prior turns. Filter out anything that isn't user/assistant — the
    # OpenAI-style schema rejects unknown roles, and there's no point
    # forwarding tool/system messages from earlier turns to a fresh prompt.
    for m in state.history:
        if m.role in (MessageRole.USER, MessageRole.ASSISTANT):
            messages.append({"role": m.role.value, "content": m.content})

    # The new user message comes last so the model knows what to respond to.
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


async def save_turn_node(state: ChatState) -> dict:
    """Persist the user message and the AI reply.

    Runs LAST so a failure here doesn't poison the in-memory state. If
    persistence fails we still return a usable assistant_message to the
    caller; the conversation just won't be re-readable later.
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

def build_chat_graph():
    """Construct the 4-node graph:
        load_history → retrieve → answer → save_turn → END.

    Compiled once, reused for every request.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ChatState)

    graph.add_node("load_history", load_history_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("answer", answer_node)
    graph.add_node("save_turn", save_turn_node)

    graph.add_edge(START, "load_history")
    graph.add_edge("load_history", "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", "save_turn")
    graph.add_edge("save_turn", END)

    return graph.compile()


# Module-level compiled graph. Recompiling per request is fine perf-wise but
# wasteful; cache it.
_compiled_graph = None


def get_chat_graph():
    """Lazy singleton accessor for the compiled graph.

    Why lazy: langgraph imports torch transitively in some configs, so we
    only pay the cold-start cost when something actually wants the chat.
    """
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
    """Run one user message through the graph and return the final state.

    Returns the FINAL state. Callers read ``state.assistant_message`` for the
    reply and ``state.conversation_id`` if they need to reference the row.
    """
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
        retrieved_chunks=result.get("retrieved_chunks", []),
        assistant_message=result.get("assistant_message", ""),
    )
