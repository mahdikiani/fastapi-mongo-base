"""Tests for Motor/PyMongo-compatible aggregation helper."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fastapi_mongo_base.utils.mongo_aggregate import aggregate_to_list


@pytest.mark.asyncio
async def test_aggregate_to_list_beanie2_pymongo_collection() -> None:
    """Beanie 2: use get_pymongo_collection; aggregate/to_list may be sync."""
    docs = [{"_id": 1}]
    cursor = MagicMock()
    cursor.to_list.return_value = docs
    collection = MagicMock()
    collection.aggregate.return_value = cursor
    model = MagicMock(spec=["get_pymongo_collection"])
    model.get_pymongo_collection.return_value = collection
    model.__name__ = "Doc"

    result = await aggregate_to_list(model, [{"$match": {}}], length=10)

    assert result == docs
    model.get_pymongo_collection.assert_called_once_with()
    collection.aggregate.assert_called_once_with([{"$match": {}}])
    cursor.to_list.assert_called_once_with(length=10)


@pytest.mark.asyncio
async def test_aggregate_to_list_beanie1_motor_fallback() -> None:
    """Beanie 1: fall back to get_motor_collection."""
    docs = [{"_id": 2}]
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    collection = MagicMock()
    collection.aggregate = AsyncMock(return_value=cursor)
    model = MagicMock(spec=["get_motor_collection"])
    model.get_motor_collection.return_value = collection
    model.__name__ = "Doc"

    pipeline: list[dict[str, Any]] = [{"$group": {"_id": None}}]
    result = await aggregate_to_list(
        model, pipeline, length=None, allowDiskUse=True
    )

    assert result == docs
    model.get_motor_collection.assert_called_once_with()
    collection.aggregate.assert_awaited_once_with(pipeline, allowDiskUse=True)
    cursor.to_list.assert_awaited_once_with(length=None)


@pytest.mark.asyncio
async def test_aggregate_to_list_missing_collection_getter() -> None:
    """Raise when the model exposes neither collection getter."""
    model = MagicMock(spec=[])
    model.__name__ = "Broken"

    with pytest.raises(AttributeError, match="get_pymongo_collection"):
        await aggregate_to_list(model, [])
