from datetime import datetime

from beanie import (
    Document,
    Insert,
    Replace,
    Save,
    SaveChanges,
    Update,
    before_event,
)
from beanie.odm.queries.find import FindMany
from pydantic import ConfigDict
from pymongo import ASCENDING, IndexModel

from .core.config import Settings
from .schemas import (
    BaseEntitySchema,
    TenantScopedEntitySchema,
    TenantUserEntitySchema,
    UserOwnedEntitySchema,
)
from .utils import basic, timezone


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
            # Use `__dict__` to check if `__abstract__` is defined
            # in the class itself
            return (
                "__abstract__" in cls.__dict__ and cls.__dict__["__abstract__"]
            )

    @before_event([Insert, Replace, Save, SaveChanges, Update])
    async def pre_save(self):
        self.updated_at = datetime.now(timezone.tz)

    @classmethod
    def get_queryset(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        **kwargs,
    ) -> dict:
        """Build a MongoDB query filter based on provided parameters.

        Args:
            user_id: Filter by user ID if the model has user_id field
            tenant_id: Filter by tenant ID if the model has tenant_id field
            is_deleted: Filter by deletion status
            uid: Filter by unique identifier
            **kwargs: Additional filters that can include range queries
                      with _from/_to suffixes

        Returns:
            List of MongoDB query conditions
        """
        # Start with basic filters
        base_query = {}

        # Add standard filters if applicable
        base_query.update({"is_deleted": is_deleted})

        if hasattr(cls, "tenant_id") and tenant_id:
            base_query.update({"tenant_id": tenant_id})

        if hasattr(cls, "user_id") and user_id:
            base_query.update({"user_id": user_id})

        if uid:
            base_query.update({"uid": uid})

        # Process additional filters from kwargs
        for key, value in kwargs.items():
            if value is None:
                continue

            # Extract base field name without suffixes
            base_field = basic.get_base_field_name(key)

            # Validate field is allowed for searching
            if (
                cls.search_field_set()
                and base_field not in cls.search_field_set()  # noqa: W503
            ):
                continue
            if (
                cls.search_exclude_set()
                and base_field in cls.search_exclude_set()  # noqa: W503
            ):
                continue
            if not hasattr(cls, base_field):
                continue

            # Handle range queries and array operators
            if key.endswith("_from") or key.endswith("_to"):
                if basic.is_valid_range_value(value):
                    op = "$gte" if key.endswith("_from") else "$lte"
                    base_query.setdefault(base_field, {}).update({op: value})
            elif key.endswith("_in") or key.endswith("_nin"):
                value_list = basic.parse_array_parameter(value)
                operator = "$in" if key.endswith("_in") else "$nin"
                base_query.update({base_field: {operator: value_list}})
            else:
                base_query.update({key: value})

        return base_query

    @classmethod
    def get_query(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        created_at_from: datetime = None,
        created_at_to: datetime = None,
        **kwargs,
    ) -> FindMany:
        base_query = cls.get_queryset(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            uid=uid,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            **kwargs,
        )
        query = cls.find(base_query)
        return query

    @classmethod
    async def get_item(
        cls,
        *,
        uid: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs,
    ) -> "BaseEntity":
        query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            uid=uid,
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
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        offset: int = 0,
        limit: int = 10,
        is_deleted: bool = False,
        **kwargs,
    ):
        offset, limit = cls.adjust_pagination(offset, limit)

        query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )

        items_query = query.sort("-created_at").skip(offset).limit(limit)
        items = await items_query.to_list()
        return items

    @classmethod
    async def total_count(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs,
    ):
        query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )
        return await query.count()

    @classmethod
    async def list_total_combined(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        offset: int = 0,
        limit: int = 10,
        is_deleted: bool = False,
        **kwargs,
    ) -> tuple[list["BaseEntity"], int]:
        items = await cls.list_items(
            user_id=user_id,
            tenant_id=tenant_id,
            offset=offset,
            limit=limit,
            is_deleted=is_deleted,
            **kwargs,
        )
        total = await cls.total_count(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )

        return items, total

    @classmethod
    async def get_by_uid(cls, uid: str):
        item = await cls.find_one({"uid": uid})
        return item

    @classmethod
    async def create_item(cls, data: dict):
        pop_keys = []
        for key in data.keys():
            if cls.create_field_set() and key not in cls.create_field_set():
                pop_keys.append(key)
            elif cls.create_exclude_set() and key in cls.create_exclude_set():
                pop_keys.append(key)

        for key in pop_keys:
            data.pop(key, None)

        data["created_at"] = datetime.now(timezone.tz)
        data["updated_at"] = datetime.now(timezone.tz)

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


class UserOwnedEntity(UserOwnedEntitySchema, BaseEntity):
    class Settings(BaseEntity.Settings):
        __abstract__ = True

        indexes = BaseEntity.Settings.indexes + [
            IndexModel([
                ("user_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        user_id: str | None = None,
        ignore_user_id: bool = False,
        **kwargs,
    ) -> "UserOwnedEntity":
        """Get an item by its UID and user ID.

        Args:
            uid (str): The unique identifier of the item
            user_id (str | None, optional):
                       The user ID to filter by.
                       Defaults to None.
            ignore_user_id (bool, optional):
                       Whether to ignore the user_id filter. Defaults to False.
            **kwargs: Additional keyword arguments to pass
                      to the parent get_item method

        Returns:
            UserOwnedEntity: The found item

        Raises:
            ValueError: If user_id is required but not provided
        """
        if user_id is None and not ignore_user_id:
            raise ValueError("user_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            **kwargs,
        )


class TenantScopedEntity(TenantScopedEntitySchema, BaseEntity):
    class Settings(BaseEntity.Settings):
        __abstract__ = True

        indexes = BaseEntity.Settings.indexes + [
            IndexModel([
                ("tenant_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        *,
        uid: str,
        tenant_id: str,
        **kwargs,
    ) -> "TenantScopedEntity":
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        return await super().get_item(
            uid=uid,
            tenant_id=tenant_id,
            **kwargs,
        )

    async def get_tenant(self):
        raise NotImplementedError


class TenantUserEntity(TenantUserEntitySchema, BaseEntity):
    class Settings(TenantScopedEntity.Settings):
        __abstract__ = True

        indexes = UserOwnedEntity.Settings.indexes + [
            IndexModel([
                ("tenant_id", ASCENDING),
                ("user_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        *,
        uid: str,
        tenant_id: str,
        user_id: str | None = None,
        ignore_user_id: bool = False,
        **kwargs,
    ) -> "TenantUserEntity":
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if user_id is None and not ignore_user_id:
            raise ValueError("user_id is required")
        return await BaseEntity.get_item(
            uid=uid,
            tenant_id=tenant_id,
            user_id=user_id,
            **kwargs,
        )


class ImmutableMixin(BaseEntity):
    model_config = ConfigDict(frozen=True)

    class Settings(BaseEntity.Settings):
        __abstract__ = True

    @classmethod
    async def update_item(cls, item: "BaseEntity", data: dict):
        raise ValueError("Immutable items cannot be updated")

    @classmethod
    async def delete_item(cls, item: "BaseEntity"):
        raise ValueError("Immutable items cannot be deleted")
