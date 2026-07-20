"""Pydantic schemas for entities and responses."""

from datetime import datetime
from typing import Generic, TypeVar

import uuid6
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator
from typing_extensions import Self

from .core.config import Settings
from .i18n.timezone import serialize_response_datetime
from .utils import timezone


class BaseEntitySchema(BaseModel):
    """Base Pydantic schema for entities with common fields and validation."""

    uid: str = Field(
        default_factory=lambda: str(uuid6.uuid7()),
        json_schema_extra={"index": True, "unique": True},
        description="Unique identifier for the entity",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.tz),
        json_schema_extra={"index": True},
        description="Date and time the entity was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.tz),
        json_schema_extra={"index": True},
        description="Date and time the entity was last updated",
    )
    is_deleted: bool = Field(
        default=False,
        description="Whether the entity has been deleted",
    )
    meta_data: dict | None = Field(
        default=None,
        description="Additional metadata for the entity",
    )

    model_config = ConfigDict(from_attributes=True, validate_assignment=True)

    @field_serializer("created_at", "updated_at", when_used="json")
    def serialize_datetimes(self, dt: datetime) -> str:
        """Serialize entity timestamps in the request timezone."""
        return serialize_response_datetime(dt)

    def __hash__(self) -> int:
        """Compute hash based on serialized model."""
        return hash(self.model_dump_json())

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """Fields excluded on create operations."""
        return ["uid", "created_at", "updated_at", "is_deleted"]

    @classmethod
    def create_field_set(cls) -> list:
        """Return allowed fields for creation (empty means all)."""
        return []

    @classmethod
    def update_exclude_set(cls) -> list:
        """Fields excluded on update operations."""
        return ["uid", "created_at", "updated_at"]

    @classmethod
    def update_field_set(cls) -> list:
        """Return allowed fields for update (empty means all)."""
        return []

    @classmethod
    def search_exclude_set(cls) -> list[str]:
        """Fields excluded from search filters."""
        return ["meta_data"]

    @classmethod
    def search_field_set(cls) -> list:
        """Return allowed fields for search (empty means all)."""
        return []

    def expired(self, days: int = 3) -> bool:
        """
        Check if entity has not been updated for specified days.

        Args:
            days: Number of days to check (default: 3).

        Returns:
            True if entity is expired, False otherwise.

        """
        return (datetime.now(timezone.tz) - self.updated_at).days > days

    @property
    def item_url(self) -> str:
        """
        API URL for this entity item.

        Returns:
            Full URL string to the entity endpoint.

        """
        return "/".join([
            f"https://{Settings.root_url}{Settings.base_path}",
            f"{self.__class__.__name__.lower()}s",
            f"{self.uid}",
        ])


class OwnerOverrideCreateMixin(BaseModel):
    """Optional user owner override on create payloads (service/admin)."""

    user_id: str | None = Field(
        None,
        description="Target user id (omitted = authenticated user)",
    )


class OwnedOverrideCreateMixin(BaseModel):
    """Optional owner override on create payloads (service/admin)."""

    owner_id: str | None = Field(
        None,
        description="Target owner id (omitted = authenticated owner)",
    )


class WorkspaceOverrideCreateMixin(BaseModel):
    """Optional workspace override on create payloads (service/admin)."""

    workspace_id: str | None = Field(
        None,
        description="Target workspace id (omitted = authenticated workspace)",
    )


class UserOwnedEntitySchema(BaseEntitySchema):
    """Schema for entities owned by a user."""

    user_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for user-owned entities."""
        return [*super().update_exclude_set(), "user_id"]


class OwnedEntitySchema(BaseEntitySchema):
    """Schema for entities owned by an entity."""

    owner_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for owned entities."""
        return [*super().update_exclude_set(), "owner_id"]


class TenantScopedEntitySchema(BaseEntitySchema):
    """Schema for entities scoped to a tenant."""

    tenant_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for tenant-scoped entities."""
        return [*super().update_exclude_set(), "tenant_id"]


class TenantUserEntitySchema(TenantScopedEntitySchema, UserOwnedEntitySchema):
    """Schema for entities scoped to both tenant and user."""

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for tenant-user entities."""
        return list({*super().update_exclude_set(), "tenant_id", "user_id"})


class WorkspaceOwnedEntitySchema(BaseEntitySchema):
    """Schema for entities owned by a workspace."""

    workspace_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for workspace-owned entities."""
        return [*super().update_exclude_set(), "workspace_id"]


class TenantWorkspaceEntitySchema(
    TenantScopedEntitySchema, WorkspaceOwnedEntitySchema
):
    """Schema for entities scoped to tenant and workspace."""

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for tenant-workspace entities."""
        return list({
            *super().update_exclude_set(),
            "tenant_id",
            "workspace_id",
        })


class TenantSubjectEntitySchema(TenantScopedEntitySchema):
    """Tenant resource owned by exactly one of user or workspace."""

    user_id: str | None = None
    workspace_id: str | None = None

    @model_validator(mode="after")
    def validate_subject_xor(self) -> Self:
        """Require exactly one of user_id or workspace_id."""
        has_user = self.user_id is not None
        has_workspace = self.workspace_id is not None
        if has_user == has_workspace:
            msg = "Exactly one of user_id or workspace_id must be set"
            raise ValueError(msg)
        return self

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for tenant-subject entities."""
        return list({
            *super().update_exclude_set(),
            "tenant_id",
            "user_id",
            "workspace_id",
        })


class TenantOwnedEntitySchema(TenantScopedEntitySchema, OwnedEntitySchema):
    """
    Schema for entities scoped to both tenant and owned by an entity.

    .. deprecated::
        Use :class:`TenantWorkspaceEntitySchema` or
        :class:`TenantSubjectEntitySchema` instead. ``owner_id`` is ambiguous
        (user vs workspace vs tenant).
    """

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Fields excluded on update for tenant-owned entities."""
        return list({*super().update_exclude_set(), "tenant_id", "owner_id"})


TSchema = TypeVar("TSchema", bound=BaseModel)


class PaginatedResponse(BaseModel, Generic[TSchema]):
    """Generic paginated response model for list endpoints."""

    heads: dict[str, dict[str, str]] = Field(default_factory=dict)
    items: list[TSchema]
    total: int
    offset: int = Field(default=0)
    limit: int = Field(default=Settings.page_max_limit)

    @model_validator(mode="before")
    @classmethod
    def validate_total(cls, values: dict[str, object]) -> dict[str, object]:
        """Validate the total value."""
        if values.get("total") is None:
            values["total"] = len(values.get("items", []))
        return values

    @model_validator(mode="after")
    def validate_heads(self) -> Self:
        """
        Auto-generate heads dictionary from item fields if not provided.

        Returns:
            Self with heads populated.

        """
        if self.heads:
            return self
        if not self.items:
            return self
        self.heads = {
            field: {"en": field.replace("_", " ").title()}
            for field in self.items[0].__class__.model_fields
        }
        return self


class MultiLanguageString(BaseModel):
    """Localized string with default API locales."""

    en: str
    fa: str

    def to_localized(self) -> dict[str, str]:
        """Return locale-keyed values for API responses."""
        return {"en": self.en, "fa": self.fa}
