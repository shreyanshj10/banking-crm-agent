"""Fixtures for the DB-backed tool tests.

These tests run against the seeded local database (see the Commands section in
.claude/CLAUDE.md). If the database isn't reachable/migrated or hasn't been
seeded, skip them with an actionable message instead of failing with a confusing
connection or assertion error. The pure `logic/` tests have no such dependency.
"""

import pytest
from sqlalchemy import func, select

from app.db.connection import async_session_factory
from app.db.models import Customer


@pytest.fixture(autouse=True)
async def _require_seeded_db():
    """Skip DB-backed tests cleanly when the database isn't ready."""
    try:
        async with async_session_factory() as session:
            customer_count = await session.scalar(select(func.count()).select_from(Customer))
    except Exception as exc:  # not reachable / not migrated
        pytest.skip(f"DB-backed tests need a reachable, migrated database ({exc}).")
    if not customer_count:
        pytest.skip(
            "DB-backed tests need seeded data — run `alembic upgrade head` "
            "then `python data/generate_seed.py`."
        )
    yield
