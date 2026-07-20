"""SQLAlchemy base models and session hook (optional ``[sql]`` extra)."""

from .models import (
    BaseEntity,
    ImmutableMixin,
    OwnedEntity,
    TenantOwnedEntity,
    TenantScopedEntity,
    TenantSubjectEntity,
    TenantUserEntity,
    TenantWorkspaceEntity,
    UserOwnedEntity,
    WorkspaceOwnedEntity,
)
from .session import async_session, get_db_session

__all__ = [
    "BaseEntity",
    "ImmutableMixin",
    "OwnedEntity",
    "TenantOwnedEntity",
    "TenantScopedEntity",
    "TenantSubjectEntity",
    "TenantUserEntity",
    "TenantWorkspaceEntity",
    "UserOwnedEntity",
    "WorkspaceOwnedEntity",
    "async_session",
    "get_db_session",
]
