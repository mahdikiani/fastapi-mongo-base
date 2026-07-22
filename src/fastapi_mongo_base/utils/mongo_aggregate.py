"""Mongo aggregation helpers compatible with Motor and PyMongo async."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beanie import Document


async def aggregate_to_list(
    model: type[Document],
    pipeline: list[dict[str, object]],
    *,
    length: int | None = None,
    **kwargs: object,
) -> list[dict[str, object]]:
    """
    Run an aggregation pipeline and return documents as a list.

    Beanie's ``aggregate().to_list()`` assumes Motor cursors; PyMongo 4.x
    native async may return a coroutine from ``aggregate()`` — this helper
    supports both drivers.
    """
    collection = model.get_motor_collection()
    cursor = collection.aggregate(pipeline, **kwargs)
    if inspect.isawaitable(cursor):
        cursor = await cursor
    result = cursor.to_list(length=length)
    if inspect.isawaitable(result):
        return await result
    return result
