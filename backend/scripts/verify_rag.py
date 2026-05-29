"""One-off: run a sample RAG retrieval against Dhaka Dental.

Run from backend/ with:
    .venv\\Scripts\\python scripts\\verify_rag.py
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.core.database import async_session_factory
from app.services.rag import retrieve_relevant


# Dhaka Dental's UUID from the seed data.
DHAKA_DENTAL_ID = UUID("dc37dd35-bc92-4e6e-bce1-596b01a17a42")

QUERIES = [
    "do you do root canals",
    "what are your hours on saturday",
    "how much does a cleaning cost",
    "i want to book an appointment for tooth pain",
]


async def main() -> None:
    async with async_session_factory() as db:
        for q in QUERIES:
            print(f"\nQuery: {q!r}")
            results = await retrieve_relevant(
                db,
                business_id=DHAKA_DENTAL_ID,
                query=q,
                top_k=3,
            )
            if not results:
                print("  (no results)")
                continue
            for i, chunk in enumerate(results, start=1):
                content_preview = chunk.content[:80].replace("\n", " ")
                print(
                    f"  {i}. [{chunk.source_type.value:7}] "
                    f"d={chunk.distance:.3f}  {content_preview!r}"
                )


if __name__ == "__main__":
    asyncio.run(main())
