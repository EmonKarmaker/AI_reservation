"""One-off: set a business's escalation_email by slug.

Usage:
    .venv\\Scripts\\python scripts\\set_escalation_email.py <slug> <email>

Example:
    .venv\\Scripts\\python scripts\\set_escalation_email.py dhaka-dental me@example.com

Behavior:
- Finds the Business by slug. Exits with code 2 if not found.
- Finds or creates the BusinessSetting row for that business.
- Sets escalation_email and commits.
- Idempotent: re-running with the same email is a no-op (in effect).

Pulls from the project's normal async DB session — no need to pass a
connection string.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.business import Business
from app.models.business_setting import BusinessSetting


async def main(slug: str, email: str) -> int:
    async with async_session_factory() as db:
        # Resolve business
        result = await db.execute(select(Business).where(Business.slug == slug))
        business = result.scalar_one_or_none()
        if business is None:
            print(f"ERROR: no business with slug {slug!r}", file=sys.stderr)
            return 2

        # Find or create the settings row
        result = await db.execute(
            select(BusinessSetting).where(BusinessSetting.business_id == business.id)
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            setting = BusinessSetting(
                business_id=business.id,
                escalation_email=email,
            )
            db.add(setting)
            action = "created"
        else:
            setting.escalation_email = email
            action = "updated"

        await db.commit()

        print(
            f"OK: {action} business_settings for {business.name} (slug={slug}); "
            f"escalation_email set."
        )
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/set_escalation_email.py <slug> <email>",
            file=sys.stderr,
        )
        sys.exit(2)

    exit_code = asyncio.run(main(sys.argv[1], sys.argv[2]))
    sys.exit(exit_code)
