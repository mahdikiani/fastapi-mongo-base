"""SQLAlchemy AuditLog twin (table created only when audit is enabled)."""

from __future__ import annotations

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..sql.models import ImmutableMixin, TenantScopedEntity

AUDIT_LOG_TABLE = "audit_logs"

_sql_audit_activated: bool = False


class AuditLog(TenantScopedEntity, ImmutableMixin):
    """
    Append-only SQL audit log row.

    Always declared so metadata knows the table, but only created/used when
    ``AUDIT_LOG_ENABLED`` activates auditing at SQL init.
    """

    __tablename__ = AUDIT_LOG_TABLE
    __audit_log__ = True

    action: Mapped[str] = mapped_column(String(32), index=True)
    resource_type: Mapped[str] = mapped_column(String(128), index=True)
    resource_uid: Mapped[str] = mapped_column(String(64), index=True)

    actor_user_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    actor_workspace_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    actor_sub_type: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    actor_principal_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    resource_user_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    resource_workspace_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    resource_owner_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """Allow tenant_id and audit fields on internal create."""
        return ["uid", "created_at", "updated_at", "is_deleted"]


def get_sql_audit_log_model() -> type | None:
    """Return the SQL AuditLog model when auditing is activated."""
    if not _sql_audit_activated:
        return None
    return AuditLog


def activate_sql_audit_log() -> type:
    """Mark the SQL AuditLog model as active for emission/create_tables."""
    global _sql_audit_activated
    _sql_audit_activated = True
    return AuditLog


def deactivate_sql_audit_log() -> None:
    """Mark the SQL AuditLog model inactive (tests / disabled settings)."""
    global _sql_audit_activated
    _sql_audit_activated = False
