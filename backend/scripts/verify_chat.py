"""One-off: drive a multi-turn conversation through the chat graph.

Two-turn dialogue verifies that:
1. The 4-node graph (load_history → retrieve → answer → save_turn) runs.
2. Messages are persisted (count goes from 0 → 2 → 4).
3. The second turn HAS access to history (we ask a follow-up that depends
   on the prior assistant message).

Run from backend/ with:
    .venv\\Scripts\\python scripts\\verify_chat.py
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.business import Business
from app.services.chat_graph import run_chat_turn


DHAKA_DENTAL_ID = UUID("dc37dd35-bc92-4e6e-bce1-596b01a17a42")
# Fresh customer id per script run so we always start a clean conversation.
CUSTOMER_ID = uuid4()

TURNS = [
    "How much does a routine cleaning cost?",                # expect: question
    "Great, can I book one for Saturday morning?",            # expect: booking
    "This is ridiculous, I want to speak to a manager!",      # expect: escalate
    "What are your hours on Sunday?",                         # expect: question
]


async def main() -> None:
    async with async_session_factory() as db:
        business = (
            await db.execute(select(Business).where(Business.id == DHAKA_DENTAL_ID))
        ).scalar_one()
        print(f"Business: {business.name} ({business.slug})")
        print(f"Customer:  {CUSTOMER_ID}\n")

        for i, msg in enumerate(TURNS, start=1):
            print(f"--- TURN {i} ---")
            print(f"USER: {msg}")
            state = await run_chat_turn(
                db=db,
                business_id=DHAKA_DENTAL_ID,
                business_name=business.name,
                customer_id=CUSTOMER_ID,
                user_message=msg,
                business_greeting=business.ai_greeting,
                business_personality=business.ai_personality,
            )
            print(f"  intent: {state.intent}")
            print(f"  conversation_id: {state.conversation_id}")
            print(f"  history loaded: {len(state.history)} prior messages")
            if state.retrieved_chunks:
                print(f"  retrieved: {len(state.retrieved_chunks)} chunks")
            print(f"AI: {state.assistant_message}\n")


if __name__ == "__main__":
    asyncio.run(main())
