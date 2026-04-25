"""One-off table verification — confirm Phase 1.4 migration applied correctly.

Lists every table in the ``public`` schema. Useful as a sanity check after
running ``alembic upgrade head`` and any time someone wants to confirm the
schema state of the live database.

Run from the ``backend/`` directory:

    .venv\\Scripts\\python scripts\\verify_tables.py
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.config import settings


def main() -> None:
    engine = create_engine(settings.DATABASE_URL_SYNC)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
        ).fetchall()

    print(f"table count: {len(rows)}")
    for (name,) in rows:
        print(f" - {name}")


if __name__ == "__main__":
    main()
