"""Quick diagnostic — show the langgraph_state of the most recent conversation."""
import asyncio
import json

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.conversation import Conversation


async def main():
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(Conversation)
                .order_by(Conversation.updated_at.desc())
                .limit(2)
            )
        ).scalars().all()
        for r in rows:
            print(f"conv {r.id}")
            print(f"  updated_at: {r.updated_at}")
            print(f"  state: {json.dumps(r.langgraph_state, indent=4)}")
            print()


if __name__ == "__main__":
    asyncio.run(main())