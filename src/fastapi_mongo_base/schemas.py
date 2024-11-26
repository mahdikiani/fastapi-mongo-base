import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

try:
    from server.config import Settings
except ImportError:

    class Settings:
        root_url = "localhost:8000"


class CoreEntitySchema(BaseModel):
    created_at: datetime = Field(
        default_factory=datetime.now, json_schema_extra={"index": True}
    )
    updated_at: datetime = Field(default_factory=datetime.now)
    is_deleted: bool = False
    meta_data: dict[str, Any] | None = None


class BaseEntitySchema(CoreEntitySchema):
    uid: uuid.UUID = Field(
        default_factory=uuid.uuid4, json_schema_extra={"index": True, "unique": True}
    )

    @property
    def item_url(self):
        return (
            f"https://{Settings.root_url}/{self.__class__.__name__.lower()}s/{self.uid}"
        )

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
        return []

    @classmethod
    def search_field_set(cls) -> list:
        return ["uid", "is_deleted", "user_id", "business_name"]

    def expired(self, days: int = 3):
        return (datetime.now() - self.updated_at).days > days


class OwnedEntitySchema(BaseEntitySchema):
    user_id: uuid.UUID

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return super().create_exclude_set() + ["user_id"]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return super().update_exclude_set() + ["user_id"]


class BusinessEntitySchema(BaseEntitySchema):
    business_name: str

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return super().create_exclude_set() + ["business_name"]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return super().update_exclude_set() + ["business_name"]


class BusinessOwnedEntitySchema(OwnedEntitySchema, BusinessEntitySchema):

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return list(set(super().create_exclude_set() + ["business_name", "user_id"]))

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return list(set(super().update_exclude_set() + ["business_name", "user_id"]))


class Language(str, Enum):
    English = "English"
    Persian = "Persian"


T = TypeVar("T", bound=BaseEntitySchema)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int
