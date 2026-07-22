"""Pydantic schema for audit log entries."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from ..schemas import TenantScopedEntitySchema


class AuditAction(str, Enum):
    """Supported audit actions for resource mutations."""

    create = "create"
    update = "update"
    delete = "delete"


class AuditLogSchema(TenantScopedEntitySchema):
    """
    Append-only audit record for a resource mutation.

    Distinguishes the acting principal from resource ownership fields.
    """

    action: AuditAction = Field(description="Mutation action performed")
    resource_type: str = Field(description="Model / resource type name")
    resource_uid: str = Field(description="UID of the affected resource")

    actor_user_id: str | None = Field(
        default=None,
        description="User id of the actor when applicable",
    )
    actor_workspace_id: str | None = Field(
        default=None,
        description="Workspace context of the actor when applicable",
    )
    actor_sub_type: str | None = Field(
        default=None,
        description="Actor kind: user, agent, api_key, ...",
    )
    actor_principal_id: str | None = Field(
        default=None,
        description="Stable principal id (e.g. JWT sub / uid)",
    )

    resource_user_id: str | None = Field(
        default=None,
        description="Resource user_id ownership copy for filtering",
    )
    resource_workspace_id: str | None = Field(
        default=None,
        description="Resource workspace_id ownership copy",
    )
    resource_owner_id: str | None = Field(
        default=None,
        description="Resource owner_id ownership copy",
    )

    changes: dict[str, dict[str, object]] | None = Field(
        default=None,
        description="Sparse field diff: {field: {old, new}}",
    )
    snapshot_before: dict[str, object] | None = Field(
        default=None,
        description="Full resource snapshot before the mutation",
    )
    snapshot_after: dict[str, object] | None = Field(
        default=None,
        description="Full resource snapshot after the mutation",
    )
    trace_id: str | None = Field(
        default=None,
        description="Request trace id when available",
    )

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """Audit rows use internal create; inherit base exclude set."""
        return [*super().create_exclude_set()]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Audit rows are immutable; exclude all mutable domain fields."""
        return [
            *super().update_exclude_set(),
            "action",
            "resource_type",
            "resource_uid",
            "actor_user_id",
            "actor_workspace_id",
            "actor_sub_type",
            "actor_principal_id",
            "resource_user_id",
            "resource_workspace_id",
            "resource_owner_id",
            "changes",
            "snapshot_before",
            "snapshot_after",
            "trace_id",
            "tenant_id",
        ]
