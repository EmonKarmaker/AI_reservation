"""Count rows by demo entity to confirm seed worked. Run from ``backend/``:

    .venv\\Scripts\\python scripts\\verify_demo_data.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.database import async_session_factory, engine
from app.models.business import Business
from app.models.faq import Faq
from app.models.operating_hours import OperatingHours
from app.models.service import Service
from app.models.user import User


async def main() -> None:
    async with async_session_factory() as session:
        counts = {
            "businesses": (await session.execute(select(func.count(Business.id)))).scalar(),
            "users":      (await session.execute(select(func.count(User.id)))).scalar(),
            "services":   (await session.execute(select(func.count(Service.id)))).scalar(),
            "hours":      (await session.execute(select(func.count(OperatingHours.id)))).scalar(),
            "faqs":       (await session.execute(select(func.count(Faq.id)))).scalar(),
        }

    for key, value in counts.items():
        print(f"  {key}: {value}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
