"""Emit audit log rows for resource mutations."""

from __future__ import annotations

import logging
from typing import Any

from .context import get_audit_actor, is_audit_enabled
from .diff import compute_changes, serialize_value
from .schemas import AuditAction

logger = logging.getLogger(__name__)

_SNAPSHOT_EXCLUDE = frozenset({
    "id",
    "_id",
    "revision_id",
})


def _is_audit_log_instance(item: object) -> bool:
    return bool(getattr(type(item), "__audit_log__", False))


def _is_sql_entity(item: object) -> bool:
    return hasattr(type(item), "__tablename__")


def dump_entity(item: object) -> dict[str, object]:
    """Serialize an entity to a plain dict for snapshots/diffs."""
    if hasattr(item, "model_dump"):
        data = item.model_dump()
    elif hasattr(item, "dump"):
        data = item.dump()
    else:
        data = {
            key: getattr(item, key)
            for key in dir(item)
            if not key.startswith("_") and not callable(getattr(item, key))
        }
    if not isinstance(data, dict):
        return {}
    return {
        key: serialize_value(value)
        for key, value in data.items()
        if key not in _SNAPSHOT_EXCLUDE
    }


def _resource_ownership(item: object) -> dict[str, str | None]:
    return {
        "resource_user_id": getattr(item, "user_id", None),
        "resource_workspace_id": getattr(item, "workspace_id", None),
        "resource_owner_id": getattr(item, "owner_id", None),
    }


def _resolve_tenant_id(item: object) -> str:
    tenant_id = getattr(item, "tenant_id", None)
    if tenant_id:
        return str(tenant_id)
    actor = get_audit_actor()
    if actor and actor.tenant_id:
        return actor.tenant_id
    return "system"


def _trace_id() -> str | None:
    try:
        from ..utils.trace import get_trace_id

        return get_trace_id()
    except Exception:
        return None


def build_audit_payload(
    *,
    action: AuditAction | str,
    item: object,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the keyword payload for an AuditLog create."""
    action_value = (
        action.value if isinstance(action, AuditAction) else str(action)
    )
    after_snap = after if after is not None else dump_entity(item)
    before_snap = before

    if action_value == AuditAction.create.value:
        changes = compute_changes(None, after_snap)
        snapshot_before = None
        snapshot_after = after_snap
    elif action_value == AuditAction.delete.value:
        changes = compute_changes(before_snap or after_snap, after_snap)
        if not changes and before_snap is not None:
            changes = {
                "is_deleted": {
                    "old": False,
                    "new": True,
                },
            }
        snapshot_before = before_snap or after_snap
        snapshot_after = after_snap
    else:
        changes = compute_changes(before_snap, after_snap)
        snapshot_before = before_snap
        snapshot_after = after_snap

    actor = get_audit_actor()
    ownership = _resource_ownership(item)
    return {
        "tenant_id": _resolve_tenant_id(item),
        "action": action_value,
        "resource_type": type(item).__name__,
        "resource_uid": str(getattr(item, "uid", "")),
        "actor_user_id": actor.user_id if actor else None,
        "actor_workspace_id": actor.workspace_id if actor else None,
        "actor_sub_type": actor.sub_type if actor else None,
        "actor_principal_id": actor.principal_id if actor else None,
        "resource_user_id": ownership["resource_user_id"],
        "resource_workspace_id": ownership["resource_workspace_id"],
        "resource_owner_id": ownership["resource_owner_id"],
        "changes": changes or None,
        "snapshot_before": snapshot_before,
        "snapshot_after": snapshot_after,
        "trace_id": _trace_id(),
    }


async def record_audit(
    *,
    action: AuditAction | str,
    item: object,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> object | None:
    """
    Persist an audit log row for ``item``.

    Chooses Mongo or SQL backend based on the entity type.
    """
    if _is_audit_log_instance(item):
        return None

    payload = build_audit_payload(
        action=action,
        item=item,
        before=before,
        after=after,
    )

    if _is_sql_entity(item):
        from .sql import get_sql_audit_log_model

        model = get_sql_audit_log_model()
        if model is None:
            logger.warning(
                "SQL audit enabled but AuditLog model is not activated",
            )
            return None
        return await model.create_item(payload)

    from .models import AuditLog

    return await AuditLog.create_item(payload)


async def maybe_record_audit(
    *,
    action: AuditAction | str,
    item: object,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
) -> object | None:
    """Record an audit row when auditing is enabled; never raise."""
    if not is_audit_enabled():
        return None
    try:
        return await record_audit(
            action=action,
            item=item,
            before=before,
            after=after,
        )
    except Exception:
        logger.exception(
            "Failed to record audit log action=%s resource=%s",
            action,
            type(item).__name__,
        )
        return None


def snapshot_for_audit(item: object) -> dict[str, Any]:
    """Public helper to capture pre-mutation state for updates/deletes."""
    return dump_entity(item)
