"""MongoDB AuditLog document (registered only when audit is enabled)."""

from __future__ import annotations

from typing import ClassVar

from pymongo import ASCENDING, IndexModel
from typing_extensions import Never, Self

from ..models import TenantScopedEntity
from .schemas import AuditLogSchema

AUDIT_LOG_COLLECTION = "audit_logs"


class AuditLog(AuditLogSchema, TenantScopedEntity):
    """
    Append-only tenant-scoped audit log document.

    Kept abstract by default so Beanie discovery skips it until
    ``AUDIT_LOG_ENABLED`` activates registration at Mongo init.

    Not based on ``ImmutableMixin`` because its frozen pydantic config breaks
    Beanie's post-insert ``id`` assignment; mutators are blocked explicitly.
    """

    __audit_log__ = True

    class Settings(TenantScopedEntity.Settings):
        """Beanie settings: abstract until activated."""

        name = AUDIT_LOG_COLLECTION
        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *TenantScopedEntity.Settings.indexes,
            IndexModel([
                ("tenant_id", ASCENDING),
                ("resource_type", ASCENDING),
                ("resource_uid", ASCENDING),
                ("created_at", ASCENDING),
            ]),
            IndexModel([
                ("tenant_id", ASCENDING),
                ("actor_user_id", ASCENDING),
                ("created_at", ASCENDING),
            ]),
            IndexModel([
                ("tenant_id", ASCENDING),
                ("action", ASCENDING),
                ("created_at", ASCENDING),
            ]),
        ]

    @classmethod
    async def update_item(cls, item: Self, data: dict) -> Never:
        """Prevent updates to audit log rows."""
        raise ValueError("Audit log items cannot be updated")

    @classmethod
    async def delete_item(cls, item: Self) -> Never:
        """Prevent deletes of audit log rows."""
        raise ValueError("Audit log items cannot be deleted")


def activate_mongo_audit_log() -> type[AuditLog]:
    """Make ``AuditLog`` a concrete Beanie document for init_beanie."""
    AuditLog.Settings.__abstract__ = False
    return AuditLog


def deactivate_mongo_audit_log() -> None:
    """Mark ``AuditLog`` abstract again (tests / teardown)."""
    AuditLog.Settings.__abstract__ = True
