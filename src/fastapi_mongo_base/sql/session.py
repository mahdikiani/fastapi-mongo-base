"""
SQLAlchemy async session hook for application wiring.

Applications normally rely on ``db.init_sql()`` to assign ``async_session``.
Use ``get_db_session()`` as a FastAPI dependency or async context manager.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

try:
    pass
except ImportError as e:
    raise ImportError("SQLAlchemy is not installed") from e

from typing import TYPE_CHECKING

from fastapi_mongo_base.errors.sql import SQLConnectionError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

async_session: async_sessionmaker[AsyncSession] | None = None


def require_async_session() -> async_sessionmaker[AsyncSession]:
    """Return the session factory or raise if SQL was not initialized."""
    if async_session is None:
        raise SQLConnectionError(
            "SQL async session is not initialized. "
            "Configure DATABASE_URI and ensure init_sql() ran at startup."
        )
    return async_session


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """
    Yield an async SQLAlchemy session.

    Raises:
        SQLConnectionError: When SQL has not been initialized.

    """
    session_factory = require_async_session()
    async with session_factory() as session:
        yield session
