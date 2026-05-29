"""Conversation + Message persistence helpers.

A Conversation is a single chat session for one (business, customer) pair.
Messages append to it in order. The graph reads recent history before
calling the LLM and writes back the user message + AI reply at the end of
every turn.

Customer identity: for Phase 4 we use a free-form UUID (``customer_id``)
that the frontend will generate per browser session (cookie). No login is
required to chat. Anonymous chats just use a fresh UUID.

The Message model's Postgres column ``metadata`` is exposed in Python as
``extra_data`` (per the schema gotcha) — we never write to it from this
file. Empty dict default is fine.
"""

from __future__ import annotations

import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.enums import ConversationChannel, ConversationStatus, MessageRole
from app.models.message import Message


# Cap how many messages we feed back to the LLM. Bigger = better memory but
# more tokens. 10 covers a normal back-and-forth without bloating context.
DEFAULT_HISTORY_LIMIT = 10


async def _ensure_customer_exists(
    db: AsyncSession,
    *,
    customer_id: UUID,
    business_id: UUID,
) -> None:
    """Ensure a Customer row exists for ``customer_id`` in ``business_id``.

    The chatbot serves anonymous visitors who don't have contact info when
    they start typing. We provision a placeholder Customer row on first
    contact so the conversations FK constraint is satisfied. Phase 4.6's
    booking flow will later update full_name/email/phone with real values
    once the customer commits to a booking.

    Idempotent — re-runs after the row exists are no-ops. customer_id is the
    primary key of the customers row (same UUID the frontend will pass in).
    """
    existing = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if existing is not None:
        return

    # Placeholder name + synthetic email so admins can spot anonymous chat
    # customers later. The customers table has a check constraint
    # ck_customers_email_or_phone requiring at least one contact field, so
    # we provide a synthetic email. The `chat.local` domain is non-routable
    # and unambiguously not real. When the customer later books and
    # provides a real email, the booking flow updates this row.
    placeholder_name = f"Anonymous (cust-{str(customer_id)[:8]})"
    placeholder_email = f"anon-{customer_id}@chat.local"
    db.add(
        Customer(
            id=customer_id,
            business_id=business_id,
            full_name=placeholder_name,
            email=placeholder_email,
        )
    )
    await db.commit()


async def get_or_create_conversation(
    db: AsyncSession,
    *,
    business_id: UUID,
    customer_id: UUID,
    channel: ConversationChannel = ConversationChannel.CHAT,
) -> Conversation:
    """Find an active conversation for this (business, customer) or open a new one.

    'Active' means status == ACTIVE. Closed/escalated conversations are not
    reopened; the next message starts a fresh row. This matches how real
    chat UIs work — you don't resume an old thread, you start a new one.
    """
    # Ensure the FK target row exists before inserting a conversation.
    # No-op if the customer was already created in a prior turn.
    await _ensure_customer_exists(
        db, customer_id=customer_id, business_id=business_id
    )

    result = await db.execute(
        select(Conversation).where(
            Conversation.business_id == business_id,
            Conversation.customer_id == customer_id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    conversation = Conversation(
        business_id=business_id,
        customer_id=customer_id,
        channel=channel,
        status=ConversationStatus.ACTIVE,
        # session_token is NOT NULL on the table with no DB default.
        # 32 url-safe bytes = ~43 chars; collision-resistant and opaque to
        # the client (the frontend will use this as a reconnect handle in
        # Phase 4.7).
        session_token=secrets.token_urlsafe(32),
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_recent_messages(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[Message]:
    """Return the most recent ``limit`` messages, oldest first.

    Oldest-first ordering is what the LLM wants — chat history is a
    chronological transcript. We query newest-first + reverse to LIMIT
    efficiently on the DB side.
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()
    return rows


async def append_message(
    db: AsyncSession,
    *,
    conversation_id: UUID,
    role: MessageRole,
    content: str,
) -> Message:
    """Append one message to a conversation and commit."""
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message
