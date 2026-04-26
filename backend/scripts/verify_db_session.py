"""One-off DB session verification — confirms Phase 1.6 plumbing works end-to-end.

Opens a session via the configured async session factory and runs a no-op
SELECT 1 against Supabase. Run from the ``backend/`` directory:

    .venv\\Scripts\\python scripts\\verify_db_session.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.database import async_session_factory, engine


async def main() -> None:
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT 1 AS one"))
        value = result.scalar_one()
        print(f"db says: {value}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
