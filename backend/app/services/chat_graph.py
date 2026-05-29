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
from app.services.rag import RetrievedChunk, retrieve_relevant


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

@dataclass
class ChatState:
    """State carried across all graph nodes.

    Inputs (set by the caller before invoke):
    - ``db``           : Active async session (the graph needs DB access for RAG).
    - ``business_id``  : Tenant whose embeddings to search.
    - ``business_name``: Used in the system prompt so the AI knows who it represents.
    - ``business_greeting`` : Optional. The business's configured AI greeting.
    - ``business_personality`` : Optional. The business's configured AI personality.
    - ``user_message`` : The customer's latest message.

    Populated by graph execution:
    - ``retrieved_chunks`` : RAG results (populated by 'retrieve' node).
    - ``assistant_message``: Final LLM reply (populated by 'answer' node).
    """

    # Required inputs
    db: AsyncSession
    business_id: UUID
    business_name: str
    user_message: str

    # Optional inputs
    business_greeting: str | None = None
    business_personality: str | None = None

    # Filled by nodes
    retrieved_chunks: list[RetrievedChunk] = field(default_factory=list)
    assistant_message: str = ""


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def retrieve_node(state: ChatState) -> dict:
    """Retrieve top-k relevant embeddings for the user's message.

    Pure RAG step — no LLM call here. Wraps retrieve_relevant from Phase 4.2.
    """
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
    """Call the LLM with the user message + system prompt and return the reply."""
    system_prompt = _build_system_prompt(state)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": state.user_message},
    ]

    try:
        reply = await chat_completion(messages, temperature=0.3)
    except Exception as exc:  # noqa: BLE001
        # Best-effort fallback. We never want a chatbot to 500.
        logger.warning("LLM call failed in answer_node: %s", exc)
        reply = (
            "I'm having trouble answering that right now. Could you try again "
            "in a moment, or contact us directly?"
        )

    return {"assistant_message": reply}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_chat_graph():
    """Construct the 3-node graph: retrieve → answer → END.

    Compiled at module import time (cached). Each request reuses the compiled
    graph; only the per-request state is fresh.

    Returns a compiled LangGraph runnable. The caller invokes via
    ``await graph.ainvoke(initial_state)``.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ChatState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("answer", answer_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "answer")
    graph.add_edge("answer", END)

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
    user_message: str,
    business_greeting: str | None = None,
    business_personality: str | None = None,
) -> ChatState:
    """Run one user message through the graph and return the final state.

    Convenience wrapper for callers (verification scripts, the future
    /chat endpoint) so they don't have to assemble ChatState themselves.

    Returns the FINAL state, from which the caller reads
    ``state.assistant_message`` to send back to the user.
    """
    graph = get_chat_graph()

    initial_state = ChatState(
        db=db,
        business_id=business_id,
        business_name=business_name,
        user_message=user_message,
        business_greeting=business_greeting,
        business_personality=business_personality,
    )

    # LangGraph's ainvoke can return either a dict or the state class
    # depending on version; normalise to ChatState by re-hydrating.
    result = await graph.ainvoke(initial_state)
    if isinstance(result, ChatState):
        return result

    # Result is dict-like. Build a fresh ChatState carrying the final values.
    return ChatState(
        db=db,
        business_id=business_id,
        business_name=business_name,
        user_message=user_message,
        business_greeting=business_greeting,
        business_personality=business_personality,
        retrieved_chunks=result.get("retrieved_chunks", []),
        assistant_message=result.get("assistant_message", ""),
    )
