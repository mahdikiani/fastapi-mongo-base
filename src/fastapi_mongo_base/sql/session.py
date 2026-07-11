"""
SQLAlchemy async session hook for application wiring.

Applications normally rely on ``db.init_sql()`` to assign ``async_session``.
Use ``get_db_session()`` as a FastAPI dependency or async context manager.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
except ImportError as e:
    raise ImportError("SQLAlchemy is not installed") from e

from ..errors.sql import SQLConnectionError

async_session: sessionmaker[AsyncSession] | None = None


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """
    Yield an async SQLAlchemy session.

    Raises:
        SQLConnectionError: When SQL has not been initialized.

    """
    if async_session is None:
        raise SQLConnectionError(
            "SQL async session is not initialized. "
            "Configure DATABASE_URI and ensure init_sql() ran at startup."
        )
    async with async_session() as session:
        yield session
