"""Async database engine and session factory.

Async only — there is no synchronous engine anywhere in this project. The URL
comes from `settings.database_url` (must be the `postgresql+asyncpg://` form).
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Single async engine for the whole app (connection pooling handled by SQLAlchemy).
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

# Session factory. expire_on_commit=False so objects stay usable after commit
# (important for async request handlers returning ORM data).
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
