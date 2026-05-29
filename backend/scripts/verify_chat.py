"""One-off: drive a few real chat turns through the Phase 4.3 graph.

Hits Dhaka Dental with several realistic customer questions and prints both
the retrieved chunks (so we can see RAG is working) and the LLM answer (so
we can see grounding is working).

Run from backend/ with:
    .venv\\Scripts\\python scripts\\verify_chat.py
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.business import Business
from app.services.chat_graph import run_chat_turn


DHAKA_DENTAL_ID = UUID("dc37dd35-bc92-4e6e-bce1-596b01a17a42")

QUESTIONS = [
    "Hi! Do you do root canals?",
    "How much does a routine cleaning cost?",
    "What are your hours on Saturday?",
    "Can you do open-heart surgery?",  # out-of-scope; should refuse gracefully
]


async def main() -> None:
    async with async_session_factory() as db:
        business = (
            await db.execute(select(Business).where(Business.id == DHAKA_DENTAL_ID))
        ).scalar_one()
        print(f"Business: {business.name} ({business.slug})")
        print(f"Personality: {business.ai_personality or '(none set)'}\n")

        for q in QUESTIONS:
            print(f"USER: {q}")
            state = await run_chat_turn(
                db=db,
                business_id=DHAKA_DENTAL_ID,
                business_name=business.name,
                user_message=q,
                business_greeting=business.ai_greeting,
                business_personality=business.ai_personality,
            )
            print(f"  retrieved: {len(state.retrieved_chunks)} chunks")
            for i, c in enumerate(state.retrieved_chunks[:2], start=1):
                snippet = c.content[:70].replace("\n", " ")
                print(f"    {i}. [{c.source_type.value}] d={c.distance:.3f}  {snippet!r}")
            print(f"AI: {state.assistant_message}\n")


if __name__ == "__main__":
    asyncio.run(main())
