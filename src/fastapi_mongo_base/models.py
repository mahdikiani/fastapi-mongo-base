import uuid
from datetime import date, datetime
from decimal import Decimal

from beanie import Document, Insert, Replace, Save, SaveChanges, Update, before_event
from beanie.odm.queries.find import FindMany
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel

try:
    from server.config import Settings
except ImportError:
    from .core.config import Settings

from .schemas import (
    BaseEntitySchema,
    BusinessEntitySchema,
    BusinessOwnedEntitySchema,
    OwnedEntitySchema,
)
from .tasks import TaskMixin


class BaseEntity(BaseEntitySchema, Document):
    class Settings:
        __abstract__ = True

        keep_nulls = False
        validate_on_save = True

        indexes = [
            IndexModel([("uid", ASCENDING)], unique=True),
        ]

        @classmethod
        def is_abstract(cls):
            # Use `__dict__` to check if `__abstract__` is defined in the class itself
            return "__abstract__" in cls.__dict__ and cls.__dict__["__abstract__"]

    @before_event([Insert, Replace, Save, SaveChanges, Update])
    async def pre_save(self):
        self.updated_at = datetime.now()

    @classmethod
    def get_queryset(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        uid: uuid.UUID = None,
        created_at_from: datetime = None,
        created_at_to: datetime = None,
        *args,
        **kwargs,
    ) -> list[dict]:
        base_query = [{"is_deleted": is_deleted}]
        if hasattr(cls, "user_id") and user_id:
            base_query.append({"user_id": user_id})
        if hasattr(cls, "business_name"):
            base_query.append({"business_name": business_name})
        if uid:
            base_query.append({"uid": uid})

        for key, value in kwargs.items():
            if value is None:
                continue
            if cls.search_field_set() and key not in cls.search_field_set():
                continue
            if cls.search_exclude_set() and key in cls.search_exclude_set():
                continue
            if not hasattr(cls, key.rstrip("_from").rstrip("_to")):
                continue

            if key.endswith("_from") and isinstance(
                value, (int, float, Decimal, datetime, date, str)
            ):
                field = key[:-5]  # Remove "_from"
                base_query.append({field: {"$gte": value}})
            elif key.endswith("_to") and isinstance(
                value, (int, float, Decimal, datetime, date, str)
            ):
                field = key[:-3]  # Remove "_to"
                base_query.append({field: {"$lte": value}})
            base_query.append({key: value})

        return base_query

    @classmethod
    def get_query(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        uid: uuid.UUID = None,
        created_at_from: datetime = None,
        created_at_to: datetime = None,
        *args,
        **kwargs,
    ) -> FindMany:
        base_query = cls.get_queryset(
            user_id=user_id,
            business_name=business_name,
            is_deleted=is_deleted,
            uid=uid,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            *args,
            **kwargs,
        )
        query = cls.find(*base_query)
        return query

    @classmethod
    async def get_item(
        cls,
        uid: uuid.UUID,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ) -> "BaseEntity":
        query = cls.get_query(
            user_id=user_id,
            business_name=business_name,
            is_deleted=is_deleted,
            uid=uid,
            *args,
            **kwargs,
        )
        items = await query.to_list()
        if not items:
            return None
        if len(items) > 1:
            raise ValueError("Multiple items found")
        return items[0]

    @classmethod
    def adjust_pagination(cls, offset: int, limit: int):
        from fastapi import params

        if isinstance(offset, params.Query):
            offset = offset.default
        if isinstance(limit, params.Query):
            limit = limit.default

        offset = max(offset or 0, 0)
        limit = max(1, min(limit or 10, Settings.page_max_limit))
        return offset, limit

    @classmethod
    async def list_items(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        offset: int = 0,
        limit: int = 10,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ):
        offset, limit = cls.adjust_pagination(offset, limit)

        query = cls.get_query(
            user_id=user_id,
            business_name=business_name,
            is_deleted=is_deleted,
            *args,
            **kwargs,
        )

        items_query = query.sort("-created_at").skip(offset).limit(limit)
        items = await items_query.to_list()
        return items

    @classmethod
    async def total_count(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ):
        query = cls.get_query(
            user_id=user_id,
            business_name=business_name,
            is_deleted=is_deleted,
            *args,
            **kwargs,
        )
        return await query.count()

    @classmethod
    async def list_total_combined(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        offset: int = 0,
        limit: int = 10,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ) -> tuple[list["BaseEntity"], int]:
        items = await cls.list_items(
            user_id=user_id,
            business_name=business_name,
            offset=offset,
            limit=limit,
            is_deleted=is_deleted,
            **kwargs,
        )
        total = await cls.total_count(
            user_id=user_id,
            business_name=business_name,
            is_deleted=is_deleted,
            **kwargs,
        )

        return items, total

    @classmethod
    async def create_item(cls, data: dict):
        # for key in data.keys():
        #     if cls.create_exclude_set() and key not in cls.create_field_set():
        #         data.pop(key, None)
        #     elif cls.create_exclude_set() and key in cls.create_exclude_set():
        #         data.pop(key, None)

        item = cls(**data)
        await item.save()
        return item

    @classmethod
    async def update_item(cls, item: "BaseEntity", data: dict):
        for key, value in data.items():
            if cls.update_field_set() and key not in cls.update_field_set():
                continue
            if cls.update_exclude_set() and key in cls.update_exclude_set():
                continue

            if hasattr(item, key):
                setattr(item, key, value)

        await item.save()
        return item

    @classmethod
    async def delete_item(cls, item: "BaseEntity"):
        item.is_deleted = True
        await item.save()
        return item


class OwnedEntity(OwnedEntitySchema, BaseEntity):

    class Settings(BaseEntity.Settings):
        __abstract__ = True

        indexes = BaseEntity.Settings.indexes + [IndexModel([("user_id", ASCENDING)])]

    @classmethod
    async def get_item(cls, uid, user_id, *args, **kwargs) -> "OwnedEntity":
        if user_id == None and kwargs.get("ignore_user_id") != True:
            raise ValueError("user_id is required")
        return await super().get_item(uid, user_id=user_id, *args, **kwargs)


class BusinessEntity(BusinessEntitySchema, BaseEntity):

    class Settings(BaseEntity.Settings):
        __abstract__ = True

        indexes = BaseEntity.Settings.indexes + [
            IndexModel([("business_name", ASCENDING)])
        ]

    @classmethod
    async def get_item(cls, uid, business_name, *args, **kwargs) -> "BusinessEntity":
        if business_name == None:
            raise ValueError("business_name is required")
        return await super().get_item(uid, business_name=business_name, *args, **kwargs)

    async def get_business(self):
        raise NotImplementedError
        from apps.business_mongo.models import Business

        return await Business.get_by_name(self.business_name)


class BusinessOwnedEntity(BusinessOwnedEntitySchema, BaseEntity):

    class Settings(BusinessEntity.Settings):
        __abstract__ = True

        indexes = BusinessEntity.Settings.indexes + [
            IndexModel([("user_id", ASCENDING)])
        ]

    @classmethod
    async def get_item(
        cls, uid, business_name, user_id, *args, **kwargs
    ) -> "BusinessOwnedEntity":
        if business_name == None:
            raise ValueError("business_name is required")
        # if user_id == None:
        #     raise ValueError("user_id is required")
        return await super().get_item(
            uid, business_name=business_name, user_id=user_id, *args, **kwargs
        )


class BaseEntityTaskMixin(BaseEntity, TaskMixin):
    class Settings(BaseEntity.Settings):
        __abstract__ = True


class ImmutableBase(BaseEntity):
    model_config = ConfigDict(frozen=True)

    class Settings(BaseEntity.Settings):
        __abstract__ = True

    @classmethod
    async def update_item(cls, item: "BaseEntity", data: dict):
        raise ValueError("Immutable items cannot be updated")

    @classmethod
    async def delete_item(cls, item: "BaseEntity"):
        raise ValueError("Immutable items cannot be deleted")


class ImmutableOwnedEntity(ImmutableBase, OwnedEntity):

    class Settings(OwnedEntity.Settings):
        __abstract__ = True


class ImmutableBusinessEntity(ImmutableBase, BusinessEntity):

    class Settings(BusinessEntity.Settings):
        __abstract__ = True


class ImmutableBusinessOwnedEntity(ImmutableBase, BusinessOwnedEntity):

    class Settings(BusinessOwnedEntity.Settings):
        __abstract__ = True
