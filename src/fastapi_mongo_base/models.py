"""MongoDB entity models with Beanie ODM."""

import logging
from datetime import datetime
from typing import Any, ClassVar, cast

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
from pymongo import ASCENDING, IndexModel
from typing_extensions import Self

from .core.config import Settings
from .schemas import (
    BaseEntitySchema,
    OwnedEntitySchema,
    TenantOwnedEntitySchema,
    TenantScopedEntitySchema,
    TenantSubjectEntitySchema,
    TenantUserEntitySchema,
    TenantWorkspaceEntitySchema,
    UserOwnedEntitySchema,
    WorkspaceOwnedEntitySchema,
)
from .utils import basic, timezone

logger = logging.getLogger(__name__)


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
    def _has_field(cls, name: str) -> bool:
        """Return True if the model declares ``name`` as a field."""
        model_fields = getattr(cls, "model_fields", None)
        if model_fields is not None and name in model_fields:
            return True
        return hasattr(cls, name)

    @classmethod
    def _build_extra_filters(cls, **kwargs: object) -> dict:
        """
        Build MongoDB filter dictionary from keyword arguments.

        Supports range queries (_from, _to), list queries (_in, _nin),
        and regex queries (_like).

        Args:
            **kwargs: Filter parameters with special suffixes.

        Returns:
            Dictionary of MongoDB filter conditions.

        """
        extra_filters: dict[str, Any] = {}
        for key, value in kwargs.items():
            if value is None:
                continue
            base_field = basic.get_base_field_name(key)
            if (
                cls.search_field_set()
                and base_field not in cls.search_field_set()
            ):
                logger.warning("Key %s is not in search_field_set", key)
                continue
            if (
                cls.search_exclude_set()
                and base_field in cls.search_exclude_set()
            ):
                logger.warning("Key %s is in search_exclude_set", key)
                continue
            if not cls._has_field(base_field):
                continue
            if key.endswith(("_from", "_to")):
                if basic.is_valid_range_value(value):
                    op = "$gte" if key.endswith("_from") else "$lte"
                    extra_filters.setdefault(base_field, {}).update({
                        op: value
                    })
            elif key.endswith(("_in", "_nin")):
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
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        **kwargs: object,
    ) -> dict:
        """Build a MongoDB query filter based on provided parameters."""
        base_query: dict[str, object] = {"is_deleted": is_deleted}
        if cls._has_field("tenant_id") and tenant_id:
            base_query.update({"tenant_id": tenant_id})
        if cls._has_field("user_id") and user_id:
            base_query.update({"user_id": user_id})
        if cls._has_field("workspace_id") and workspace_id:
            base_query.update({"workspace_id": workspace_id})
        if cls._has_field("owner_id") and owner_id:
            base_query.update({"owner_id": owner_id})
        if uid:
            base_query.update({"uid": uid})
        # Extract extra filters from kwargs
        extra_filters = cls._build_extra_filters(**cast("Any", kwargs))
        base_query.update(extra_filters)
        return base_query

    @classmethod
    def get_query(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
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
            workspace_id: Optional workspace ID filter.
            owner_id: Optional owner ID filter.
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
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            uid=uid,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            **cast("Any", kwargs),
        )
        return cls.find(base_query)

    @classmethod
    async def get_item(
        cls,
        uid: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_user_id: bool = False,
        ignore_owner_id: bool = False,
        ignore_workspace_id: bool = False,
        ignore_subject: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """
        Get a single item by UID.

        Args:
            uid: Unique identifier of the item.
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            workspace_id: Optional workspace ID filter.
            owner_id: Optional owner ID filter.
            is_deleted: Filter by deletion status.
            ignore_user_id: Accepted for subclass overrides; unused here.
            ignore_owner_id: Accepted for subclass overrides; unused here.
            ignore_workspace_id: Accepted for subclass overrides; unused here.
            ignore_subject: Accepted for subclass overrides; unused here.
            **kwargs: Additional filter parameters.

        Returns:
            Entity instance if found, None otherwise.

        Raises:
            ValueError: If multiple items are found.

        """
        del ignore_user_id, ignore_owner_id
        del ignore_workspace_id, ignore_subject
        query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            uid=uid,
            **cast("Any", kwargs),
        )
        items = await query.to_list()
        if not items:
            return None
        if len(items) > 1:
            raise ValueError("Multiple items found")
        return items[0]

    @classmethod
    def adjust_pagination(
        cls, offset: int | None, limit: int | None
    ) -> tuple[int, int]:
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

        offset_value = max(offset or 0, 0)
        if limit is None:
            limit_value = max(1, min(10, Settings.page_max_limit))
        else:
            limit_value = max(1, min(limit, Settings.page_max_limit))
        return offset_value, limit_value

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
            **cast("Any", kwargs),
        )

        items_query = query.sort([
            (sort_field, cast("Any", sort_direction))
        ]).skip(offset)
        if limit:
            items_query = items_query.limit(limit)
        return await items_query.to_list()

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
            **cast("Any", kwargs),
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
                **cast("Any", kwargs),
            ),
            cls.total_count(
                user_id=user_id,
                tenant_id=tenant_id,
                is_deleted=is_deleted,
                **cast("Any", kwargs),
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
        return await cls.find_one({"uid": uid, "is_deleted": is_deleted})

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
                logger.warning("Key %s is not in create_field_set", key)
                pop_keys.append(key)
            elif cls.create_exclude_set() and key in cls.create_exclude_set():
                logger.warning("Key %s is in create_exclude_set", key)
                pop_keys.append(key)

        for key in pop_keys:
            data.pop(key, None)

        data["created_at"] = datetime.now(timezone.tz)
        data["updated_at"] = datetime.now(timezone.tz)

        item = cls(**data)
        await item.save()
        from .audit.emit import maybe_record_audit
        from .audit.schemas import AuditAction

        await maybe_record_audit(action=AuditAction.create, item=item)
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
        from .audit.context import is_audit_enabled
        from .audit.emit import maybe_record_audit, snapshot_for_audit
        from .audit.schemas import AuditAction

        before = snapshot_for_audit(item) if is_audit_enabled() else None

        for key, value in data.items():
            if cls.update_field_set() and key not in cls.update_field_set():
                logger.warning("Key %s is not in update_field_set", key)
                continue
            if cls.update_exclude_set() and key in cls.update_exclude_set():
                logger.warning("Key %s is in update_exclude_set", key)
                continue

            if hasattr(item, key):
                setattr(item, key, value)

        await item.save()
        await maybe_record_audit(
            action=AuditAction.update,
            item=item,
            before=before,
        )
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
        from .audit.context import is_audit_enabled
        from .audit.emit import maybe_record_audit, snapshot_for_audit
        from .audit.schemas import AuditAction

        before = snapshot_for_audit(item) if is_audit_enabled() else None
        item.is_deleted = True
        await item.save()
        await maybe_record_audit(
            action=AuditAction.delete,
            item=item,
            before=before,
        )
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
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_user_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, requiring ``user_id`` unless ignored."""
        if user_id is None and not ignore_user_id:
            raise ValueError("user_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
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
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_owner_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, requiring ``owner_id`` unless ignored."""
        if owner_id is None and not ignore_owner_id:
            raise ValueError("owner_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
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
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, requiring ``tenant_id``."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
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
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_user_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, requiring tenant and user IDs unless ignored."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if user_id is None and not ignore_user_id:
            raise ValueError("user_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )


class WorkspaceOwnedEntity(WorkspaceOwnedEntitySchema, BaseEntity):
    """Base entity class for workspace-owned resources."""

    class Settings(BaseEntity.Settings):
        """Beanie document settings with workspace_id index."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *BaseEntity.Settings.indexes,
            IndexModel([
                ("workspace_id", ASCENDING),
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
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_workspace_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID and workspace ID."""
        if workspace_id is None and not ignore_workspace_id:
            raise ValueError("workspace_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )


class TenantWorkspaceEntity(TenantWorkspaceEntitySchema, BaseEntity):
    """Base entity for tenant + workspace scoped resources."""

    class Settings(TenantScopedEntity.Settings):
        """Beanie indexes for tenant_id and workspace_id."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *WorkspaceOwnedEntity.Settings.indexes,
            IndexModel([
                ("tenant_id", ASCENDING),
                ("workspace_id", ASCENDING),
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
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_workspace_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, tenant ID, and workspace ID."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if workspace_id is None and not ignore_workspace_id:
            raise ValueError("workspace_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )


class TenantSubjectEntity(TenantSubjectEntitySchema, BaseEntity):
    """Base entity for tenant resources with user XOR workspace ownership."""

    class Settings(TenantScopedEntity.Settings):
        """Beanie indexes for tenant and subject fields."""

        __abstract__ = True

        indexes: ClassVar[list[IndexModel]] = [
            *TenantScopedEntity.Settings.indexes,
            IndexModel([
                ("tenant_id", ASCENDING),
                ("user_id", ASCENDING),
                ("uid", ASCENDING),
                ("is_deleted", ASCENDING),
            ]),
            IndexModel([
                ("tenant_id", ASCENDING),
                ("workspace_id", ASCENDING),
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
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_subject: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, tenant, and subject id."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if not ignore_subject and user_id is None and workspace_id is None:
            raise ValueError("user_id or workspace_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )


class TenantOwnedEntity(TenantOwnedEntitySchema, BaseEntity):
    """
    Base entity class for tenant-owned resources.

    Automatically filters queries by both tenant_id and owner_id.

    .. deprecated::
        Prefer :class:`TenantWorkspaceEntity` or :class:`TenantSubjectEntity`.
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
        user_id: str | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
        owner_id: str | None = None,
        is_deleted: bool = False,
        ignore_owner_id: bool = False,
        **kwargs: object,
    ) -> Self | None:
        """Get an item by UID, requiring tenant and owner IDs."""
        if tenant_id is None:
            raise ValueError("tenant_id is required")
        if owner_id is None and not ignore_owner_id:
            raise ValueError("owner_id is required")
        return await super().get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            owner_id=owner_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )


class ImmutableMixin(BaseEntity):
    """Mixin class for immutable entities that cannot be updated or deleted."""

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
        del item, data
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
        del item
        raise ValueError("Immutable items cannot be deleted")
