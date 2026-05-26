"""Bootstrap a super_admin user for the platform.

Why this exists: ``POST /api/v1/auth/register`` creates business_admin users
only. The platform owner needs to be a super_admin (no business scope, full
platform access). Since super admins cannot self-register through the public
API, the first one — and any replacements — must be created out-of-band by
this script.

Usage from ``backend/``:

    .venv\\Scripts\\python scripts\\create_super_admin.py

Two modes:

1. **Env-driven (CI / production deploy).**
   If all three of these env vars are set, the script runs unattended:
       SUPER_ADMIN_EMAIL
       SUPER_ADMIN_PASSWORD
       SUPER_ADMIN_FULL_NAME
   This is the path Render's "deploy command" or a one-off CI job would use.

2. **Interactive (local development).**
   If any env var is missing, the script prompts for the missing fields.
   Password input is hidden via ``getpass`` so it does not appear on screen
   or in shell history.

Idempotency:
- If a user with the given email already exists AND has role=super_admin,
  the script offers to skip or to overwrite the password.
- If a user with the email exists but is NOT a super_admin, the script
  refuses (changing a business_admin into a super_admin via this script
  would silently strip their business_id and is not what anyone wants).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from getpass import getpass

from sqlalchemy import select

from app.core.database import async_session_factory, engine
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


# Loose RFC 5322-ish email check. Pydantic does the strict version on the
# API surface; this is just to avoid obviously-wrong inputs at the prompt.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LEN = 8


# ---------------------------------------------------------------------------
# Input collection
# ---------------------------------------------------------------------------

def _collect_inputs() -> tuple[str, str, str]:
    """Return (email, password, full_name) from env vars or interactive prompts."""
    email = os.environ.get("SUPER_ADMIN_EMAIL", "").strip()
    password = os.environ.get("SUPER_ADMIN_PASSWORD", "")
    full_name = os.environ.get("SUPER_ADMIN_FULL_NAME", "").strip()

    if not email:
        email = input("Super admin email: ").strip()
    if not _EMAIL_PATTERN.match(email):
        print(f"ERROR: '{email}' does not look like a valid email.", file=sys.stderr)
        sys.exit(2)

    if not password:
        password = getpass("Super admin password (hidden): ")
        confirm = getpass("Confirm password (hidden): ")
        if password != confirm:
            print("ERROR: passwords do not match.", file=sys.stderr)
            sys.exit(2)
    if len(password) < _MIN_PASSWORD_LEN:
        print(
            f"ERROR: password must be at least {_MIN_PASSWORD_LEN} characters.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not full_name:
        full_name = input("Full name: ").strip()
    if not full_name:
        print("ERROR: full name cannot be empty.", file=sys.stderr)
        sys.exit(2)

    return email, password, full_name


def _prompt_yes_no(question: str, default_yes: bool = False) -> bool:
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    answer = input(question + suffix).strip().lower()
    if not answer:
        return default_yes
    return answer in {"y", "yes"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _run() -> int:
    email, password, full_name = _collect_inputs()

    async with async_session_factory() as session:
        existing = await session.execute(
            select(User).where(User.email == email)
        )
        user = existing.scalar_one_or_none()

        if user is not None:
            if user.role is not UserRole.SUPER_ADMIN:
                print(
                    f"ERROR: a user already exists with email '{email}' "
                    f"but role={user.role.value}. Refusing to repurpose "
                    "an existing account. Use a different email.",
                    file=sys.stderr,
                )
                return 2

            print(f"Super admin '{email}' already exists (id={user.id}).")
            if _prompt_yes_no("Update password?", default_yes=False):
                user.password_hash = hash_password(password)
                user.full_name = full_name
                await session.commit()
                print(f"OK: password updated for super admin {user.id}")
            else:
                print("OK: no changes made.")
            return 0

        new_user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=UserRole.SUPER_ADMIN,
            business_id=None,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        print(f"OK: created super admin {new_user.id} ({new_user.email})")
        return 0


async def _main_async() -> int:
    try:
        return await _run()
    finally:
        await engine.dispose()


def main() -> None:
    sys.exit(asyncio.run(_main_async()))


if __name__ == "__main__":
    main()
