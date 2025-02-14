import json
import uuid
from datetime import date, datetime
from decimal import Decimal

from beanie import Document, Insert, Replace, Save, SaveChanges, Update, before_event
from beanie.odm.queries.find import FindMany
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel

try:
    from json_advanced import loads
except ImportError:
    from json import loads

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
    def _parse_array_parameter(cls, value) -> list:
        """Parse input value into a list, handling various input formats.

        Args:
            value: Input value that could be a JSON string, comma-separated string,
                  list, tuple, or single value

        Returns:
            list: Parsed list of values
        """
        if isinstance(value, (list, tuple)):
            return list(set(value))

        if not isinstance(value, str):
            return [value]

        # Try parsing as JSON first
        value = value.strip()
        try:
            if value.startswith("[") and value.endswith("]"):
                parsed = loads(value)
                if isinstance(parsed, list):
                    return list(set(parsed))
                return [parsed]
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback to comma-separated values
        return list(set([v.strip() for v in value.split(",") if v.strip()]))

    @classmethod
    def get_queryset(
        cls,
        user_id: uuid.UUID = None,
        business_name: str = None,
        is_deleted: bool = False,
        uid: uuid.UUID = None,
        *args,
        **kwargs,
    ) -> list[dict]:
        """Build a MongoDB query filter based on provided parameters.

        Args:
            user_id: Filter by user ID if the model has user_id field
            business_name: Filter by business name if the model has business_name field
            is_deleted: Filter by deletion status
            uid: Filter by unique identifier
            **kwargs: Additional filters that can include range queries with _from/_to suffixes

        Returns:
            List of MongoDB query conditions
        """
        # Start with basic filters
        base_query = []

        # Add standard filters if applicable
        base_query.append({"is_deleted": is_deleted})

        if hasattr(cls, "user_id") and user_id:
            base_query.append({"user_id": user_id})

        if hasattr(cls, "business_name"):
            base_query.append({"business_name": business_name})

        if uid:
            base_query.append({"uid": uid})

        # Process additional filters from kwargs
        for key, value in kwargs.items():
            if value is None:
                continue

            # Extract base field name without suffixes
            base_field = cls._get_base_field_name(key)

            # Validate field is allowed for searching
            if cls.search_field_set() and base_field not in cls.search_field_set():
                continue
            if cls.search_exclude_set() and base_field in cls.search_exclude_set():
                continue
            if not hasattr(cls, base_field):
                continue

            # Handle range queries and array operators
            if key.endswith("_from") or key.endswith("_to"):
                if cls._is_valid_range_value(value):
                    if key.endswith("_from"):
                        base_query.append({base_field: {"$gte": value}})
                    elif key.endswith("_to"):
                        base_query.append({base_field: {"$lte": value}})
            elif key.endswith("_in") or key.endswith("_nin"):
                value_list = cls._parse_array_parameter(value)
                operator = "$in" if key.endswith("_in") else "$nin"
                base_query.append({base_field: {operator: value_list}})
            else:
                base_query.append({key: value})

        return base_query

    @classmethod
    def _get_base_field_name(cls, field: str) -> str:
        """Extract the base field name by removing suffixes."""
        if field.endswith("_from"):
            return field[:-5]
        elif field.endswith("_to"):
            return field[:-3]
        elif field.endswith("_in"):
            return field[:-3]
        elif field.endswith("_nin"):
            return field[:-4]
        return field

    @classmethod
    def _is_valid_range_value(cls, value) -> bool:
        """Check if value is valid for range comparison."""
        return isinstance(value, (int, float, Decimal, datetime, date, str))

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
        query = cls.find({"$and": base_query})
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
    async def get_by_uid(cls, uid: uuid.UUID):
        item = await cls.find_one({"uid": uid})
        return item

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
