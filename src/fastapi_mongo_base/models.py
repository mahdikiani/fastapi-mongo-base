import uuid
from datetime import datetime

from beanie import Document, Insert, Replace, Save, SaveChanges, Update, before_event
from beanie.odm.queries.find import FindMany
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel

try:
    from server.config import Settings
except ImportError:

    class Settings:
        page_max_limit = 100


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
    def get_query(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        *args,
        **kwargs,
    ) -> FindMany:
        base_query = [cls.is_deleted == is_deleted]
        if hasattr(cls, "user_id") and user_id:
            base_query.append(cls.user_id == user_id)
        if hasattr(cls, "business_name"):
            base_query.append(cls.business_name == business_name)

        query = cls.find(*base_query)
        return query

    @classmethod
    async def get_item(
        cls,
        uid,
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
            *args,
            **kwargs,
        ).find(cls.uid == uid)
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
        total = await query.count()

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
