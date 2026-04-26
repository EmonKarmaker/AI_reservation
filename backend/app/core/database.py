"""Async SQLAlchemy engine, session factory, and FastAPI dependency.

One engine per process. One session per request. Standard SQLAlchemy 2.x
async pattern.

Public surface:

- ``engine`` — module-level ``AsyncEngine`` for the application
- ``async_session_factory`` — produces ``AsyncSession`` instances
- ``get_db`` — FastAPI dependency yielding a session with rollback-on-error
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Notes on the configuration:
#
# - ``pool_pre_ping=True``: Supabase free tier pauses idle databases. Pre-ping
#   issues a no-op SELECT 1 before handing out a pooled connection so we
#   detect dead connections gracefully instead of failing the user's request.
#
# - ``pool_size`` / ``max_overflow``: modest defaults that fit free hosting.
#   Render free tier has limited concurrent worker capacity anyway. Tune later.
#
# - ``echo``: log all SQL when in dev. Off in staging/prod.
#
# - ``connect_args`` for asyncpg + Supabase pgbouncer transaction pooler:
#   pgbouncer in transaction mode does not pin a backend connection to a
#   client session, so prepared statements cannot be reused across queries.
#   asyncpg by default caches prepared statements and reuses fixed names like
#   ``__asyncpg_stmt_1__``, which collide on the next pooled connection
#   (DuplicatePreparedStatementError). Two settings prevent this:
#     * ``statement_cache_size=0`` — disable client-side prepared-statement
#       caching. Tiny perf cost; correctness with the pooler.
#     * ``prepared_statement_name_func`` — randomize statement names so even
#       transient statements never collide across pooled connections.
import uuid as _uuid

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=(settings.ENVIRONMENT == "dev"),
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{_uuid.uuid4()}__",
    },
)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

# ``expire_on_commit=False`` is critical for async + FastAPI: without it,
# accessing ORM attributes after a commit triggers an implicit re-load that
# fails outside the transaction context. With it, ORM objects stay usable
# after the request handler commits and returns them in the response.
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an ``AsyncSession`` for one request.

    Rolls back on any exception raised by the handler so we never leave a
    half-applied transaction lingering. Always closes the session at the end.
    Routers and services should never call ``session.close()`` themselves.
    """
    session = async_session_factory()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
