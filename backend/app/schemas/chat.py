"""Pydantic schemas for the public chat endpoint.

The chat endpoint is anonymous — no user auth, no business-admin token. The
client (a browser, eventually a third-party site embedding our widget)
identifies itself with a UUID it generates and persists in localStorage.

If the client doesn't yet have a customer_id (very first request from this
browser), the server generates one and returns it in the response. The
client then stores that value and sends it on every subsequent request for
this business.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /chat/{business_slug}."""

    customer_id: UUID | None = Field(
        default=None,
        description=(
            "Stable per-browser identifier minted by the client. If omitted, "
            "the server generates one and returns it in the response."
        ),
    )
    message: str = Field(
        min_length=1,
        max_length=2000,
        description="The customer's chat message.",
    )


class ChatResponse(BaseModel):
    """Response body for POST /chat/{business_slug}."""

    conversation_id: UUID = Field(
        description="UUID of the active Conversation row. Same across turns "
        "until the conversation is closed."
    )
    customer_id: UUID = Field(
        description="The customer_id used for this turn. Clients should store "
        "this and resend it on subsequent requests."
    )
    message: str = Field(description="The AI receptionist's reply.")
    intent: str = Field(
        description="Classified intent: question | booking | escalate. Useful "
        "for client-side debugging or showing intent-specific UI."
    )
