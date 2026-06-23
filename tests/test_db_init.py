"""Tests for database initialization error handling."""

import pytest
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from fastapi_mongo_base.core import db
from fastapi_mongo_base.core.config import Settings
from fastapi_mongo_base.core.errors.db_errors import (
    MongoDBConnectionError,
    MongoDBConnectionTimeoutError,
)


class _FailingClient:
    def __init__(
        self,
        exc: Exception,
        *args: object,
        **kwargs: object,
    ) -> None:
        self._exc = exc

    async def server_info(self) -> None:
        raise self._exc

    def get_database(self, _name: str) -> object:
        return object()


def _client_factory(exc: Exception) -> type:
    def _factory(*args: object, **kwargs: object) -> _FailingClient:
        return _FailingClient(exc, *args, **kwargs)

    return _factory


def _settings(*, exit_on_init_failure: bool) -> Settings:
    settings = Settings()
    settings.exit_on_init_failure = exit_on_init_failure
    return settings


@pytest.mark.asyncio
async def test_init_mongo_db_raises_connection_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Init mongo db raises connection timeout error."""
    monkeypatch.setattr(
        "pymongo.AsyncMongoClient",
        _client_factory(ServerSelectionTimeoutError("connection timed out")),
    )

    with pytest.raises(MongoDBConnectionTimeoutError):
        await db.init_mongo_db(_settings(exit_on_init_failure=False))


@pytest.mark.asyncio
async def test_init_mongo_db_raises_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Init mongo db raises connection error."""
    monkeypatch.setattr(
        "pymongo.AsyncMongoClient",
        _client_factory(ConnectionFailure("could not connect")),
    )

    with pytest.raises(MongoDBConnectionError):
        await db.init_mongo_db(_settings(exit_on_init_failure=False))


@pytest.mark.asyncio
async def test_init_mongo_db_exits_on_connection_failure_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Init mongo db exits on connection failure by default."""
    monkeypatch.setattr(
        "pymongo.AsyncMongoClient",
        _client_factory(ServerSelectionTimeoutError("connection timed out")),
    )

    with pytest.raises(SystemExit) as exc_info:
        await db.init_mongo_db(_settings(exit_on_init_failure=True))

    assert exc_info.value.code == 1
