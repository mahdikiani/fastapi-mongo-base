"""MongoDB entity models with Beanie ODM."""

import logging
from datetime import datetime
from typing import Any, ClassVar, Self, cast

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
    OwnedEntitySchema,
    TenantOwnedEntitySchema,
    TenantScopedEntitySchema,
    TenantUserEntitySchema,
    UserOwnedEntitySchema,
)
from .utils import basic, timezone


class BaseEntity(BaseEntitySchema, Document):
    """
    Base entity class for MongoDB documents with Beanie ODM.

    Provides common functionality for CRUD operations, querying, and filtering.
    """

    class Settings:
        """Beanie document settings configuration."""

        __abstract__ = True

        keep_nulls = False
        validate_on_save = True

        indexes: ClassVar[list[IndexModel]] = [
            IndexModel([("uid", ASCENDING)], unique=True),
        ]

        @classmethod
        def is_abstract(cls) -> bool:
            """
            Check if this is an abstract base class.

            Returns:
                True if the class is abstract, False otherwise.

            """
            # Use `__dict__` to check if `__abstract__` is defined
            # in the class itself
            return (
                "__abstract__" in cls.__dict__ and cls.__dict__["__abstract__"]
            )

    @before_event([Insert, Replace, Save, SaveChanges, Update])
    async def pre_save(self) -> None:
        """Update the updated_at timestamp before saving."""
        self.updated_at = datetime.now(timezone.tz)

    @classmethod
    def _build_extra_filters(cls, **kwargs: dict[str, Any]) -> dict:
        """
        Build MongoDB filter dictionary from keyword arguments.

        Supports range queries (_from, _to), list queries (_in, _nin),
        and regex queries (_like).

        Args:
            **kwargs: Filter parameters with special suffixes.

        Returns:
            Dictionary of MongoDB filter conditions.

        """
        extra_filters = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            base_field = basic.get_base_field_name(key)
            if (
                cls.search_field_set()
                and base_field not in cls.search_field_set()
            ):
                logging.warning("Key %s is not in search_field_set", key)
                continue
            if (
                cls.search_exclude_set()
                and base_field in cls.search_exclude_set()
            ):
                logging.warning("Key %s is in search_exclude_set", key)
                continue
            if not hasattr(cls, base_field):
                continue
            if key.endswith("_from") or key.endswith("_to"):
                if basic.is_valid_range_value(value):
                    op = "$gte" if key.endswith("_from") else "$lte"
                    extra_filters.setdefault(base_field, {}).update({
                        op: value
                    })
            elif key.endswith("_in") or key.endswith("_nin"):
                value_list = basic.parse_array_parameter(value)
                operator = "$in" if key.endswith("_in") else "$nin"
                extra_filters.update({base_field: {operator: value_list}})
            elif key.endswith("_like"):
                extra_filters.update({base_field: {"$regex": value}})
            else:
                extra_filters.update({key: value})
        return extra_filters

    @classmethod
    def get_queryset(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        **kwargs: object,
    ) -> dict:
        """Build a MongoDB query filter based on provided parameters."""
        base_query = {}
        base_query.update({"is_deleted": is_deleted})
        if hasattr(cls, "tenant_id") and tenant_id:
            base_query.update({"tenant_id": tenant_id})
        if hasattr(cls, "user_id") and user_id:
            base_query.update({"user_id": user_id})
        if uid:
            base_query.update({"uid": uid})
        # Extract extra filters from kwargs
        extra_filters = cls._build_extra_filters(**kwargs)
        base_query.update(extra_filters)
        return base_query

    @classmethod
    def get_query(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        **kwargs: object,
    ) -> FindMany:
        """
        Build a Beanie FindMany query object.

        Args:
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            is_deleted: Filter by deletion status.
            uid: Optional unique identifier filter.
            created_at_from: Optional start date filter.
            created_at_to: Optional end date filter.
            **kwargs: Additional filter parameters.

        Returns:
            Beanie FindMany query object.

        """
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
        uid: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """
        Get a single item by UID.

        Args:
            uid: Unique identifier of the item.
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            is_deleted: Filter by deletion status.
            **kwargs: Additional filter parameters.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If multiple items are found.

        """
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
    def adjust_pagination(cls, offset: int, limit: int) -> tuple[int, int]:
        """
        Adjust and validate pagination parameters.

        Args:
            offset: Starting offset.
            limit: Maximum number of items.

        Returns:
            Tuple of (adjusted_offset, adjusted_limit).

        """
        from fastapi import params

        if isinstance(offset, params.Query):
            offset = offset.default
        if isinstance(limit, params.Query):
            limit = limit.default

        offset = max(offset or 0, 0)
        if limit is None:
            limit = max(1, min(limit or 10, Settings.page_max_limit))
        return offset, limit

    @classmethod
    async def list_items(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort_field: str = "created_at",
        sort_direction: int = -1,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> list[Self]:
        """
        List items with pagination and filtering.

        Args:
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            offset: Starting offset for pagination.
            limit: Maximum number of items to return.
            sort_field: Field name to sort by.
            sort_direction: Sort direction (1=asc, -1=desc).
            is_deleted: Filter by deletion status.
            **kwargs: Additional filter parameters.

        Returns:
            List of entity instances.

        """
        offset, limit = cls.adjust_pagination(offset, limit)

        query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )

        items_query = query.sort((sort_field, sort_direction)).skip(offset)
        if limit:
            items_query = items_query.limit(limit)
        items = await items_query.to_list()
        return items

    @classmethod
    async def total_count(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> int:
        """
        Get total count of items matching the filters.

        Args:
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            is_deleted: Filter by deletion status.
            **kwargs: Additional filter parameters.

        Returns:
            Total count of matching items.

        """
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
        **kwargs: object,
    ) -> tuple[list[Self], int]:
        """
        List items and get total count in parallel.

        Args:
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            offset: Starting offset for pagination.
            limit: Maximum number of items to return.
            is_deleted: Filter by deletion status.
            **kwargs: Additional filter parameters.

        Returns:
            Tuple of (list of items, total count).

        """
        import asyncio

        items, total = await asyncio.gather(
            cls.list_items(
                user_id=user_id,
                tenant_id=tenant_id,
                offset=offset,
                limit=limit,
                is_deleted=is_deleted,
                **kwargs,
            ),
            cls.total_count(
                user_id=user_id,
                tenant_id=tenant_id,
                is_deleted=is_deleted,
                **kwargs,
            ),
        )

        return items, total

    @classmethod
    async def get_by_uid(
        cls,
        uid: str,
        *,
        is_deleted: bool = False,
    ) -> Self | None:
        """
        Get an item by its UID.

        Args:
            uid: Unique identifier.
            is_deleted: Filter by deletion status.

        Returns:
            Entity instance if found, None otherwise.

        """
        item = await cls.find_one({"uid": uid, "is_deleted": is_deleted})
        return item

    @classmethod
    async def create_item(cls, data: dict) -> Self:
        """
        Create a new entity instance.

        Args:
            data: Dictionary of field values.

        Returns:
            Created entity instance.

        """
        pop_keys = []
        for key in data:
            if cls.create_field_set() and key not in cls.create_field_set():
                logging.warning("Key %s is not in create_field_set", key)
                pop_keys.append(key)
            elif cls.create_exclude_set() and key in cls.create_exclude_set():
                logging.warning("Key %s is in create_exclude_set", key)
                pop_keys.append(key)

        for key in pop_keys:
            data.pop(key, None)

        data["created_at"] = datetime.now(timezone.tz)
        data["updated_at"] = datetime.now(timezone.tz)

        item = cls(**data)
        await item.save()
        return item

    @classmethod
    async def update_item(cls, item: Self, data: dict) -> Self:
        """
        Update an existing entity instance.

        Args:
            item: Entity instance to update.
            data: Dictionary of fields to update.

        Returns:
            Updated entity instance.
        """
        for key, value in data.items():
            if cls.update_field_set() and key not in cls.update_field_set():
                logging.warning("Key %s is not in update_field_set", key)
                continue
            if cls.update_exclude_set() and key in cls.update_exclude_set():
                logging.warning("Key %s is in update_exclude_set", key)
                continue

            if hasattr(item, key):
                setattr(item, key, value)

        await item.save()
        return item

    @classmethod
    async def delete_item(cls, item: Self) -> Self:
        """
        Soft delete an entity by setting is_deleted to True.

        Args:
            item: Entity instance to delete.

        Returns:
            Deleted entity instance.
        """
        item.is_deleted = True
        await item.save()
        return item


class UserOwnedEntity(UserOwnedEntitySchema, BaseEntity):
    """
    Base entity class for user-owned resources.

    Automatically filters queries by user_id.
    """

    class Settings(BaseEntity.Settings):
        """Beanie document settings with user_id index."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *BaseEntity.Settings.indexes,
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
        **kwargs: object,
    ) -> Self | None:
        """
        Get an item by its UID and user ID.

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
        return cast(
            Self | None,
            await super().get_item(
                uid=uid,
                user_id=user_id,
                **kwargs,
            ),
        )


class OwnedEntity(OwnedEntitySchema, BaseEntity):
    """
    Base entity class for owned resources.

    Automatically filters queries by owner_id.
    """

    class Settings(BaseEntity.Settings):
        """Beanie document settings with owner_id index."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *BaseEntity.Settings.indexes,
            IndexModel([
                ("owner_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        owner_id: str,
        **kwargs: object,
    ) -> Self | None:
        """
        Get an item by its UID and owner ID.

        Args:
            uid: Unique identifier of the item.
            owner_id: Owner ID (required).
            **kwargs: Additional keyword arguments.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If owner_id is not provided.

        """
        if owner_id is None:
            raise ValueError("owner_id is required")
        return cast(
            Self | None,
            await super().get_item(
                uid=uid,
                owner_id=owner_id,
                **kwargs,
            ),
        )


class TenantScopedEntity(TenantScopedEntitySchema, BaseEntity):
    """
    Base entity class for tenant-scoped resources.

    Automatically filters queries by tenant_id.
    """

    class Settings(BaseEntity.Settings):
        """Beanie document settings with tenant_id index."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *BaseEntity.Settings.indexes,
            IndexModel([
                ("tenant_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        tenant_id: str,
        **kwargs: object,
    ) -> Self | None:
        """
        Get an item by UID and tenant ID.

        Args:
            uid: Unique identifier of the item.
            tenant_id: Tenant ID (required).
            **kwargs: Additional keyword arguments.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If tenant_id is not provided.

        """
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        return cast(
            Self | None,
            await super().get_item(
                uid=uid,
                tenant_id=tenant_id,
                **kwargs,
            ),
        )

    async def get_tenant(self) -> Self:
        """
        Get the tenant entity for this resource.

        Returns:
            Tenant entity instance.

        Raises:
            NotImplementedError: Must be implemented by subclasses.

        """
        raise NotImplementedError


class TenantUserEntity(TenantUserEntitySchema, BaseEntity):
    """
    Base entity class for tenant and user scoped resources.

    Automatically filters queries by both tenant_id and user_id.
    """

    class Settings(TenantScopedEntity.Settings):
        """Beanie document settings with tenant_id and user_id indexes."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *UserOwnedEntity.Settings.indexes,
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
        uid: str,
        *,
        tenant_id: str,
        user_id: str | None = None,
        ignore_user_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """
        Get an item by UID, tenant ID, and optionally user ID.

        Args:
            uid: Unique identifier of the item.
            tenant_id: Tenant ID (required).
            user_id: Optional user ID filter.
            ignore_user_id: Whether to ignore user_id requirement.
            **kwargs: Additional keyword arguments.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If tenant_id or user_id is required but not provided.

        """
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if user_id is None and not ignore_user_id:
            raise ValueError("user_id is required")
        return cast(
            Self | None,
            await super().get_item(
                uid=uid,
                tenant_id=tenant_id,
                user_id=user_id,
                **kwargs,
            ),
        )


class TenantOwnedEntity(TenantOwnedEntitySchema, BaseEntity):
    """
    Base entity class for tenant-owned resources.

    Automatically filters queries by both tenant_id and owner_id.
    """

    class Settings(TenantScopedEntity.Settings):
        """Beanie document settings with tenant_id and owner_id indexes."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *OwnedEntity.Settings.indexes,
            IndexModel([
                ("tenant_id", ASCENDING),
                ("owner_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
        ]

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        tenant_id: str,
        owner_id: str,
        ignore_owner_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """
        Get an item by UID, tenant ID, and owner ID.

        Args:
            uid: Unique identifier of the item.
            tenant_id: Tenant ID (required).
            owner_id: Owner ID (required).
            ignore_owner_id: Whether to ignore the owner_id filter.
            **kwargs: Additional keyword arguments.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If tenant_id or owner_id is not provided.

        """
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if owner_id is None and not ignore_owner_id:
            raise ValueError("owner_id is required")
        return cast(
            Self | None,
            await super().get_item(
                uid=uid,
                tenant_id=tenant_id,
                owner_id=owner_id,
                **kwargs,
            ),
        )


class ImmutableMixin(BaseEntity):
    """Mixin class for immutable entities that cannot be updated or deleted."""

    model_config = ConfigDict(frozen=True)

    class Settings(BaseEntity.Settings):
        """Beanie document settings for immutable entities."""

        __abstract__ = True

    @classmethod
    async def update_item(cls, item: Self, data: dict) -> Self:
        """
        Prevent updating immutable items.

        Args:
            item: Entity instance.
            data: Update data.

        Raises:
            ValueError: Always raised for immutable items.

        """
        raise ValueError("Immutable items cannot be updated")

    @classmethod
    async def delete_item(cls, item: Self) -> Self:
        """
        Prevent deleting immutable items.

        Args:
            item: Entity instance.

        Raises:
            ValueError: Always raised for immutable items.

        """
        raise ValueError("Immutable items cannot be deleted")
