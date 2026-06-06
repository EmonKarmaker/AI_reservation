"""One-off: fix Dhaka Dental demo data.

- Sets businesses.currency to BDT (was seeded as USD by mistake).
- Soft-deletes the leftover ``test`` service from the menu.

Idempotent: safe to re-run. Run with::

    .venv\\Scripts\\python scripts\\fix_demo_data.py

from the backend/ directory.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.business import Business
from app.models.service import Service


DHAKA_DENTAL_SLUG = "dhaka-dental"
TARGET_CURRENCY = "BDT"
STALE_SERVICE_NAME = "test"


async def main() -> None:
    async with async_session_factory() as db:
        # Fetch the business.
        bus_result = await db.execute(
            select(Business).where(Business.slug == DHAKA_DENTAL_SLUG)
        )
        business = bus_result.scalar_one_or_none()
        if business is None:
            print(f"Business not found: slug={DHAKA_DENTAL_SLUG}")
            return

        # 1) Fix currency.
        if business.currency != TARGET_CURRENCY:
            print(
                f"Updating currency for {business.name}: "
                f"{business.currency} -> {TARGET_CURRENCY}"
            )
            business.currency = TARGET_CURRENCY
        else:
            print(f"Currency already {TARGET_CURRENCY} — skipping.")

        # 2) Soft-delete the stale "test" service.
        svc_result = await db.execute(
            select(Service).where(
                Service.business_id == business.id,
                Service.name == STALE_SERVICE_NAME,
                Service.deleted_at.is_(None),
            )
        )
        stale_services = svc_result.scalars().all()
        if stale_services:
            now = datetime.now(timezone.utc)
            for svc in stale_services:
                print(f"Soft-deleting service: {svc.name!r} (id={svc.id})")
                svc.deleted_at = now
        else:
            print(f"No active service named {STALE_SERVICE_NAME!r} — skipping.")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
