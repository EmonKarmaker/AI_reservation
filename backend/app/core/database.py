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
from sqlalchemy.pool import NullPool

from app.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# Use NullPool so SQLAlchemy does NOT pool asyncpg connections itself.
# Supabase's pgbouncer (transaction pool mode) is already pooling connections
# on the server side, and reusing asyncpg connections through pgbouncer in
# transaction mode causes prepared-statement-name collisions
# (InvalidSQLStatementNameError) once the engine has served more than one
# request. With NullPool, each request opens a fresh asyncpg connection
# through pgbouncer and closes it at end of request, so prepared statements
# never outlive a single transaction.
#
# We still set statement_cache_size=0 as a belt-and-suspenders measure;
# asyncpg's per-connection cache is irrelevant when each connection is short
# lived, but explicit > implicit.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=(settings.ENVIRONMENT == "dev"),
    connect_args={
        "statement_cache_size": 0,
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
