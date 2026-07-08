"""Tests for MongoDB initialization."""

import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import ServerSelectionTimeoutError

from src.fastapi_mongo_base.core.db import init_mongo_db
from src.fastapi_mongo_base.core.errors.mongodb_errors import (
    MongoDBConnectionError,
)


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
            "src.fastapi_mongo_base.core.db.init_beanie",
            new_callable=AsyncMock,
        ),
    ):
        await init_mongo_db(settings)

    mock_ctor.assert_called_once_with(
        settings.mongo_uri,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=2000,
    )
