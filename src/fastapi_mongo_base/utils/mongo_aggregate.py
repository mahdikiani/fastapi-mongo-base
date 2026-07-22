"""Mongo aggregation helpers compatible with Motor and PyMongo async."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beanie import Document


def _get_collection(model: type[Document]) -> object:
    """Return the Beanie collection (Beanie 2 pymongo or Beanie 1 motor)."""
    getter = getattr(model, "get_pymongo_collection", None) or getattr(
        model, "get_motor_collection", None
    )
    if getter is None:
        raise AttributeError(
            f"{model.__name__} has neither get_pymongo_collection "
            "nor get_motor_collection"
        )
    return getter()


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
    supports both drivers. Collection access works with Beanie 2
    (``get_pymongo_collection``) and Beanie 1 (``get_motor_collection``).
    """
    collection = _get_collection(model)
    cursor = collection.aggregate(pipeline, **kwargs)
    if inspect.isawaitable(cursor):
        cursor = await cursor
    result = cursor.to_list(length=length)
    if inspect.isawaitable(result):
        return await result
    return result
