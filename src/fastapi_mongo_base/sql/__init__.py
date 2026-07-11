"""SQLAlchemy base models and session hook (optional ``[sql]`` extra)."""

from .models import (
    BaseEntity,
    ImmutableMixin,
    OwnedEntity,
    TenantOwnedEntity,
    TenantScopedEntity,
    TenantUserEntity,
    UserOwnedEntity,
)
from .session import async_session, get_db_session

__all__ = [
    "BaseEntity",
    "ImmutableMixin",
    "OwnedEntity",
    "TenantOwnedEntity",
    "TenantScopedEntity",
    "TenantUserEntity",
    "UserOwnedEntity",
    "async_session",
    "get_db_session",
]
