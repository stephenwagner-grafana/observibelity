"""Async SQLAlchemy engine + session factory.

`DATABASE_URL` is expected in `postgresql+asyncpg://...` form. The kube manifest
injects it via env (host=postgres, db=observibelity, user=postgres). For local
dev, default to a sane localhost URL so `uvicorn --reload` doesn't crash on
import.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = logging.getLogger(__name__)

_DEFAULT_URL = "postgresql+asyncpg://postgres:postgres@postgres:5432/observibelity"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_URL)

# Pool sized small — Phase 1 is single-replica + low concurrency.
_engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    future=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


def get_engine() -> AsyncEngine:
    """Module-level accessor (used by tests + lifespan)."""
    return _engine


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession with auto-close. Caller commits if needed."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency injection helper."""
    async with SessionLocal() as session:
        yield session


async def ping() -> bool:
    """Cheap readiness probe — `SELECT 1` against the pool."""
    from sqlalchemy import text

    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — readiness wants the boolean
        log.warning("postgres ping failed: %s", exc)
        return False


async def dispose() -> None:
    """Called from lifespan shutdown."""
    await _engine.dispose()
