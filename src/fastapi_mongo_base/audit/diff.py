"""Diff helpers for audit change payloads."""

from __future__ import annotations

from typing import Any

import json_advanced as json


def serialize_value(value: object) -> object:
    """
    Convert a value into a JSON-friendly audit representation.

    Uses ``json_advanced`` so datetime, UUID, ObjectId, Decimal, Pydantic
    models, and other special types serialize consistently with the rest of
    the package.
    """
    return json.loads(json.dumps(value))


_DEFAULT_EXCLUDE = frozenset({
    "id",
    "_id",
    "revision_id",
})


def compute_changes(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    *,
    exclude_fields: set[str] | frozenset[str] | None = None,
) -> dict[str, dict[str, object]]:
    """
    Compute a sparse ``{field: {old, new}}`` diff between two snapshots.

    Args:
        before: State before mutation (None for create).
        after: State after mutation (None for delete).
        exclude_fields: Extra field names to ignore.

    Returns:
        Dictionary of changed fields.

    """
    excluded = set(_DEFAULT_EXCLUDE)
    if exclude_fields:
        excluded.update(exclude_fields)

    before = before or {}
    after = after or {}
    keys = (set(before) | set(after)) - excluded
    changes: dict[str, dict[str, object]] = {}
    for key in sorted(keys):
        old = serialize_value(before.get(key))
        new = serialize_value(after.get(key))
        if old != new:
            changes[key] = {"old": old, "new": new}
    return changes
