"""Diagnostic: print the most recent Booking rows.

Run with `.venv\\Scripts\\python scripts\\check_bookings.py` from the
backend/ directory. Same shape as check_state.py — top N most-recent rows,
formatted for human inspection. Read-only.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.booking import Booking


async def main() -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Booking)
            .order_by(Booking.created_at.desc())
            .limit(3)
        )
        rows = result.scalars().all()
        if not rows:
            print("(no bookings yet)")
            return
        for b in rows:
            status_val = b.status.value if hasattr(b.status, "value") else str(b.status)
            print(f"Booking {b.id}")
            print(f"  status            = {status_val}")
            print(f"  starts_at (UTC)   = {b.starts_at.isoformat()}")
            print(f"  ends_at   (UTC)   = {b.ends_at.isoformat()}")
            print(f"  total_amount      = {b.total_amount} {b.currency}")
            print(f"  business_id       = {b.business_id}")
            print(f"  customer_id       = {b.customer_id}")
            print(f"  service_id        = {b.service_id}")
            print(f"  conversation_id   = {b.conversation_id}")
            print(f"  idempotency_key   = {b.idempotency_key}")
            print(f"  created_at        = {b.created_at.isoformat()}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
