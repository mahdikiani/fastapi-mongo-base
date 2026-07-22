"""Tests for Motor/PyMongo-compatible aggregation helper."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fastapi_mongo_base.utils.mongo_aggregate import aggregate_to_list


@pytest.mark.asyncio
async def test_aggregate_to_list_sync_cursor_and_to_list() -> None:
    """Motor-style: aggregate and to_list are both synchronous."""
    docs = [{"_id": 1}]
    cursor = MagicMock()
    cursor.to_list.return_value = docs
    collection = MagicMock()
    collection.aggregate.return_value = cursor
    model = MagicMock()
    model.get_motor_collection.return_value = collection

    result = await aggregate_to_list(model, [{"$match": {}}], length=10)

    assert result == docs
    collection.aggregate.assert_called_once_with([{"$match": {}}])
    cursor.to_list.assert_called_once_with(length=10)


@pytest.mark.asyncio
async def test_aggregate_to_list_awaitable_cursor_and_to_list() -> None:
    """PyMongo async-style: both aggregate and to_list are awaitable."""
    docs = [{"_id": 2}]
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=docs)
    collection = MagicMock()
    collection.aggregate = AsyncMock(return_value=cursor)
    model = MagicMock()
    model.get_motor_collection.return_value = collection

    pipeline: list[dict[str, Any]] = [{"$group": {"_id": None}}]
    result = await aggregate_to_list(
        model, pipeline, length=None, allowDiskUse=True
    )

    assert result == docs
    collection.aggregate.assert_awaited_once_with(pipeline, allowDiskUse=True)
    cursor.to_list.assert_awaited_once_with(length=None)
