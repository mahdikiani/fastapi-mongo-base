"""Tests for MongoDB initialization."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from src.fastapi_mongo_base.core.db import (
    check_mongodb,
    check_redis,
    check_sql,
    close_sql,
    init_mongo_db,
    init_redis,
    init_sql,
)
from src.fastapi_mongo_base.errors.mongodb import (
    MongoDBConnectionError,
)
from src.fastapi_mongo_base.errors.redis import RedisConnectionError
from src.fastapi_mongo_base.errors.sql import SQLConnectionError
from src.fastapi_mongo_base.sql.session import get_db_session


@dataclasses.dataclass
class _TestMongoSettings:
    mongo_uri: str = "mongodb://unreachable:27017"
    project_name: str = "test"
    mongo_server_selection_timeout_ms: int = 1000
    mongo_connect_timeout_ms: int = 1000


@pytest.mark.asyncio
async def test_init_mongo_db_raises_on_connection_failure() -> None:
    """Startup must fail fast when MongoDB is unreachable."""
    mock_client = MagicMock()
    mock_client.server_info = AsyncMock(
        side_effect=ServerSelectionTimeoutError("timed out"),
    )

    with (
        patch("pymongo.AsyncMongoClient", return_value=mock_client),
        pytest.raises(
            MongoDBConnectionError, match="Failed to connect to MongoDB"
        ),
    ):
        await init_mongo_db(_TestMongoSettings())


@pytest.mark.asyncio
async def test_init_mongo_db_passes_timeout_options() -> None:
    """Mongo client must be created with configured timeout values."""
    mock_client = MagicMock()
    mock_client.server_info = AsyncMock(return_value={"ok": 1})
    mock_client.get_database.return_value = MagicMock()

    settings = _TestMongoSettings(
        mongo_server_selection_timeout_ms=3000,
        mongo_connect_timeout_ms=2000,
    )

    with (
        patch(
            "pymongo.AsyncMongoClient", return_value=mock_client
        ) as mock_ctor,
        patch(
            "src.fastapi_mongo_base.db.mongo.init_beanie",
            new_callable=AsyncMock,
        ),
    ):
        await init_mongo_db(settings)

    mock_ctor.assert_called_once_with(
        settings.mongo_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=2000,
    )


@pytest.mark.asyncio
async def test_check_mongodb_returns_up_on_ping() -> None:
    """Readiness check should report up when ping succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})

    assert await check_mongodb(mock_client) == "up"


@pytest.mark.asyncio
async def test_check_mongodb_returns_down_on_failure() -> None:
    """Readiness check should report down when ping fails."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=RuntimeError("down"))

    assert await check_mongodb(mock_client) == "down"
    assert await check_mongodb(None) == "down"


@pytest.mark.asyncio
async def test_check_redis_returns_up_on_ping() -> None:
    """Readiness check should report up when Redis ping succeeds."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(return_value=True)

    assert await check_redis(mock_client) == "up"


@pytest.mark.asyncio
async def test_check_redis_returns_down_on_failure() -> None:
    """Readiness check should report down when Redis ping fails."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(side_effect=RuntimeError("down"))

    assert await check_redis(mock_client) == "down"
    assert await check_redis(None) == "down"


def test_init_redis_returns_none_without_uri() -> None:
    """Redis init should no-op when REDIS_URI is not configured."""
    sync_client, async_client = init_redis(_TestMongoSettings())
    assert sync_client is None
    assert async_client is None


def test_init_redis_raises_on_connection_failure() -> None:
    """Startup must fail fast when Redis is configured but unreachable."""
    pytest.importorskip("redis")
    from redis.exceptions import RedisError

    settings = dataclasses.make_dataclass(
        "_RedisSettings",
        [
            ("redis_uri", str, "redis://unreachable:6379/0"),
            ("project_name", str, "test"),
        ],
    )()

    with (
        patch("redis.asyncio.client.Redis") as async_ctor,
        patch("redis.Redis") as sync_ctor,
        pytest.raises(
            RedisConnectionError, match="Failed to connect to Redis"
        ),
    ):
        mock_sync = MagicMock()
        mock_sync.ping.side_effect = RedisError("down")
        sync_ctor.from_url.return_value = mock_sync
        async_ctor.from_url.return_value = MagicMock()
        init_redis(settings)


@dataclasses.dataclass
class _TestSqlSettings:
    database_uri: str = "sqlite+aiosqlite:///:memory:"


@pytest.mark.asyncio
async def test_init_sql_connects_with_sqlite() -> None:
    """SQL init and readiness should work against in-memory SQLite."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")

    engine, session_factory = await init_sql(_TestSqlSettings())
    try:
        assert engine is not None
        assert session_factory is not None

        from src.fastapi_mongo_base.sql.session import async_session

        assert async_session is session_factory
        assert await check_sql(session_factory) == "up"
    finally:
        await close_sql(engine)


@pytest.mark.asyncio
async def test_get_db_session_requires_init() -> None:
    """get_db_session should fail fast when SQL is not initialized."""
    pytest.importorskip("sqlalchemy")

    with pytest.raises(SQLConnectionError, match="not initialized"):
        async with get_db_session():
            pass


@pytest.mark.asyncio
async def test_get_db_session_yields_sqlite_session() -> None:
    """get_db_session should yield a working SQLAlchemy session."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")
    from sqlalchemy import text

    engine, _session_factory = await init_sql(_TestSqlSettings())
    try:
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar_one() == 1
    finally:
        await close_sql(engine)


@pytest.mark.asyncio
async def test_init_sql_can_create_tables() -> None:
    """init_sql should optionally create tables for registered models."""
    pytest.importorskip("sqlalchemy")
    pytest.importorskip("aiosqlite")
    from sqlalchemy.orm import Mapped, mapped_column

    from src.fastapi_mongo_base.sql.models import BaseEntity

    class _SqlTestRecord(BaseEntity):
        __tablename__ = "sql_test_records"

        label: Mapped[str] = mapped_column()

    engine, _session_factory = await init_sql(
        _TestSqlSettings(),
        create_tables=True,
        metadata=BaseEntity.metadata,
    )
    try:
        from sqlalchemy import inspect

        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        assert "sql_test_records" in tables
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_conn: BaseEntity.metadata.drop_all(
                    sync_conn,
                    tables=[_SqlTestRecord.__table__],
                    checkfirst=True,
                )
            )
        await close_sql(engine)


@pytest.mark.asyncio
async def test_check_sql_returns_down_on_failure() -> None:
    """Readiness check should report down when SELECT 1 fails."""
    pytest.importorskip("sqlalchemy")
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("down"))
    mock_factory = MagicMock(return_value=mock_session)

    assert await check_sql(mock_factory) == "down"
    assert await check_sql(None) == "down"


@pytest.mark.asyncio
async def test_init_sql_returns_none_without_uri() -> None:
    """SQL init should no-op when DATABASE_URI is not configured."""
    engine, session_factory = await init_sql(_TestMongoSettings())
    assert engine is None
    assert session_factory is None
