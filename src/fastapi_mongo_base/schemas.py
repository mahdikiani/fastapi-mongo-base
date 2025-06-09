from datetime import datetime
from typing import TypeVar

import uuid6
from pydantic import BaseModel, Field

from .core.config import Settings
from .utils import timezone


class BaseEntitySchema(BaseModel):
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

    def __hash__(self):
        return hash(self.model_dump_json())

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return ["uid", "created_at", "updated_at", "is_deleted"]

    @classmethod
    def create_field_set(cls) -> list:
        return []

    @classmethod
    def update_exclude_set(cls) -> list:
        return ["uid", "created_at", "updated_at"]

    @classmethod
    def update_field_set(cls) -> list:
        return []

    @classmethod
    def search_exclude_set(cls) -> list[str]:
        return ["meta_data"]

    @classmethod
    def search_field_set(cls) -> list:
        return []

    def expired(self, days: int = 3):
        return (datetime.now(timezone.tz) - self.updated_at).days > days

    @property
    def item_url(self):
        return "/".join([
            f"https://{Settings.root_url}{Settings.base_path}",
            f"{self.__class__.__name__.lower()}s",
            f"{self.uid}",
        ])


class UserOwnedEntitySchema(BaseEntitySchema):
    user_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return super().update_exclude_set() + ["user_id"]


class TenantScopedEntitySchema(BaseEntitySchema):
    tenant_id: str

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return super().update_exclude_set() + ["tenant_id"]


class TenantUserEntitySchema(TenantScopedEntitySchema, UserOwnedEntitySchema):
    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return list(
            set(super().update_exclude_set() + ["tenant_id", "user_id"])
        )


T = TypeVar("T", bound=BaseEntitySchema)


class PaginatedResponse[T: BaseEntitySchema](BaseModel):
    items: list[T]
    total: int
    offset: int
    limit: int


class MultiLanguageString(BaseModel):
    en: str
    fa: str
