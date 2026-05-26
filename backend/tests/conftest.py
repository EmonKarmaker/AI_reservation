"""Shared pytest fixtures.

Strategy: create a fresh ``AsyncEngine`` per test and dispose it on teardown.
This avoids the classic pytest-asyncio + module-level-engine deadlock where
the engine's pool keeps connections bound to a closed event loop.

Tests commit their data to the real database. To avoid collisions with seed
data and other tests, use the ``unique_slug`` / ``unique_email`` fixtures.

A dedicated test schema or true transactional isolation is a Phase 4+
investment; for Phase 1.8c the simple approach is sufficient.

Fixtures:

- ``test_engine`` — fresh AsyncEngine per test
- ``db_session`` — AsyncSession on the fresh engine
- ``client``     — httpx.AsyncClient with get_db overridden to use db_session
- ``unique_slug`` / ``unique_email`` — collision-free test data
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.core.database import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Fresh engine per test (key change vs. the original conftest)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """A fresh AsyncEngine bound to the current test's event loop.

    The same connection-pool config as the production engine, so behavior
    matches reality. Disposed cleanly at teardown so no connections leak
    across tests.
    """
    import uuid as _uuid

    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=2,  # smaller than prod — tests don't need much
        max_overflow=0,
        echo=False,  # quieter test output
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{_uuid.uuid4()}__",
        },
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """AsyncSession bound to the per-test engine."""
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# HTTP client with DB dependency override
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient against the FastAPI app, with get_db overridden to use the
    per-test engine. A new session is opened per request — same behavior the
    app uses in production.
    """
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Test data helpers — keep tests collision-free
# ---------------------------------------------------------------------------

@pytest.fixture
def unique_slug() -> Callable[[], str]:
    def _make() -> str:
        return f"test-{uuid.uuid4().hex[:10]}"
    return _make


@pytest.fixture
def unique_email() -> Callable[[], str]:
    def _make() -> str:
        return f"test-{uuid.uuid4().hex[:10]}@example.com"
    return _make
