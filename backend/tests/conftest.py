"""Shared test fixtures."""

import pytest

from app.db.connection import engine


@pytest.fixture(autouse=True)
async def _dispose_db_engine_between_tests():
    """Dispose the async engine after each test.

    The async engine caches asyncpg connections bound to an event loop;
    pytest-asyncio uses a fresh loop per test, so without disposing, a
    connection created on one test's loop is reused on the next test's loop and
    raises "Event loop is closed". Disposing after each test keeps each test's
    connections on its own loop.
    """
    yield
    await engine.dispose()
