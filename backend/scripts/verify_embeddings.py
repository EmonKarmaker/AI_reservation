"""One-off verification: confirm embedding sync wrote rows.

Run from backend/ with: .venv\\Scripts\\python scripts\\verify_embeddings.py

Prints total embedding count, count by source_type, and a sample row per
source_type showing source_id, content snippet, and embedding[0:3].
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.core.database import async_session_factory
from app.models.embedding import Embedding


async def main() -> None:
    async with async_session_factory() as db:
        total = (await db.execute(select(func.count()).select_from(Embedding))).scalar()
        print(f"total embeddings: {total}")

        by_type = (
            await db.execute(
                select(Embedding.source_type, func.count())
                .group_by(Embedding.source_type)
                .order_by(Embedding.source_type)
            )
        ).all()
        print("by source_type:")
        for source_type, count in by_type:
            print(f"  {source_type.value}: {count}")

        print("\nsample rows:")
        for source_type_value in ("service", "faq", "business"):
            row = (
                await db.execute(
                    select(Embedding).where(Embedding.source_type == source_type_value).limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                print(f"  {source_type_value}: (none)")
                continue
            print(f"  {source_type_value}:")
            print(f"    source_id: {row.source_id}")
            print(f"    content: {row.content[:80]!r}")
            print(f"    embedding[:3]: {row.embedding[:3]}")


if __name__ == "__main__":
    asyncio.run(main())
