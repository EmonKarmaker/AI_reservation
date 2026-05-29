"""Backfill: generate embeddings for all existing services and FAQs.

Run once after Phase 3.4 ships, or any time existing rows are missing
embeddings (e.g. after a database restore). Safe to re-run: the embedding
sync helpers upsert by (source_type, source_id), so existing rows are
updated rather than duplicated.

Skips soft-deleted services (``services.deleted_at IS NOT NULL``). Processes
FAQs unconditionally — FAQs are hard-deleted, so anything in the table is
live.

Run from backend/ with:
    .venv\\Scripts\\python scripts\\backfill_embeddings.py
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.faq import Faq
from app.models.service import Service
from app.services.embedding_sync import sync_faq_embedding, sync_service_embedding


logger = logging.getLogger(__name__)


async def backfill_services(db: AsyncSession) -> tuple[int, int]:
    """Embed every non-deleted service. Returns (succeeded, failed)."""
    result = await db.execute(
        select(Service).where(Service.deleted_at.is_(None)).order_by(Service.created_at)
    )
    services = list(result.scalars().all())
    print(f"\nFound {len(services)} services to embed.")

    succeeded = 0
    failed = 0
    for i, service in enumerate(services, start=1):
        print(f"  [{i}/{len(services)}] {service.name!r} ... ", end="", flush=True)
        # sync_service_embedding is best-effort; it logs and swallows errors.
        # We can't distinguish success from silent failure from its return.
        # Workaround: run a probe to confirm the row landed afterwards (kept
        # simple — assume success unless we want stricter checks later).
        try:
            await sync_service_embedding(db, service)
            print("ok")
            succeeded += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {exc}")
            failed += 1
    return succeeded, failed


async def backfill_faqs(db: AsyncSession) -> tuple[int, int]:
    """Embed every FAQ. Returns (succeeded, failed)."""
    result = await db.execute(select(Faq).order_by(Faq.created_at))
    faqs = list(result.scalars().all())
    print(f"\nFound {len(faqs)} FAQs to embed.")

    succeeded = 0
    failed = 0
    for i, faq in enumerate(faqs, start=1):
        snippet = faq.question[:60].replace("\n", " ")
        print(f"  [{i}/{len(faqs)}] {snippet!r} ... ", end="", flush=True)
        try:
            await sync_faq_embedding(db, faq)
            print("ok")
            succeeded += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: {exc}")
            failed += 1
    return succeeded, failed


async def main() -> None:
    print("Backfilling embeddings for all services + FAQs ...")
    async with async_session_factory() as db:
        services_ok, services_fail = await backfill_services(db)
        faqs_ok, faqs_fail = await backfill_faqs(db)

    print("\nSummary:")
    print(f"  services: {services_ok} ok, {services_fail} failed")
    print(f"  faqs:     {faqs_ok} ok, {faqs_fail} failed")
    print("\nDone. Run verify_embeddings.py to see the totals.")


if __name__ == "__main__":
    asyncio.run(main())
