"""SQLAlchemy base entity classes and utilities."""

import json
import uuid
from datetime import datetime
from typing import Never, Self

try:
    from sqlalchemy import JSON, event, select
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import (
        Mapped,
        as_declarative,
        declared_attr,
        mapped_column,
        sessionmaker,
    )
    from sqlalchemy.sql import func
except ImportError as e:
    raise ImportError("SQLAlchemy is not installed") from e

from .core.config import Settings
from .utils import basic, timezone

async_session: sessionmaker[AsyncSession] = None  # type: ignore


@as_declarative()
class BaseEntity:
    """Base SQLAlchemy entity class with common fields and methods."""

    id: object
    __name__: str
    __abstract__ = True

    @declared_attr  # type: ignore
    def __tablename__(self) -> str:
        """Generate table name from class name."""
        return self.__name__.lower()

    uid: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=func.now(),
    )
    is_deleted: Mapped[bool] = mapped_column(default=False)
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude during creation."""
        return ["uid", "created_at", "updated_at", "is_deleted"]

    @classmethod
    def create_field_set(cls) -> list[str]:
        """Get list of fields to include during creation."""
        return []

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude during update."""
        return ["uid", "created_at", "updated_at"]

    @classmethod
    def update_field_set(cls) -> list[str]:
        """Get list of fields to include during update."""
        return []

    @classmethod
    def search_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude from search."""
        return ["meta_data"]

    @classmethod
    def search_field_set(cls) -> list[str]:
        """Get list of fields to include in search."""
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

    def dump(
        self,
        include_fields: list[str] | None = None,
        exclude_fields: list[str] | None = None,
    ) -> dict[str, object]:
        """
        Dump the object into a dictionary.

        It includes all the fields of the object.
        """
        result = {}
        for key in include_fields or self.__dict__.keys():
            if not hasattr(self, key):
                continue
            value = getattr(self, key)
            # Skip SQLAlchemy internal attributes
            if key.startswith("_"):
                continue
            if exclude_fields and key in exclude_fields:
                continue
            # Convert datetime objects to ISO format strings
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    def __hash__(self) -> int:
        """Generate hash from object's dictionary representation."""
        json_str = json.dumps(self.dump())
        return hash(json_str)

    @property
    def item_url(self) -> str:
        """Get the URL for this item."""
        return "/".join([
            f"https://{Settings.root_url}{Settings.base_path}",
            f"{self.__class__.__name__.lower()}s",
            f"{self.uid}",
        ])

    @classmethod
    def _range_filter(cls, field: object, key: str, value: object) -> object:
        if not basic.is_valid_range_value(value):
            return None
        if key.endswith("_from"):
            return field >= value
        elif key.endswith("_to"):
            return field <= value
        return None

    @classmethod
    def _in_nin_filter(cls, field: object, key: str, value: object) -> object:
        value_list = basic.parse_array_parameter(value)
        if key.endswith("_in"):
            return field.in_(value_list)
        elif key.endswith("_nin"):
            return ~field.in_(value_list)
        return None

    @classmethod
    def _equality_filter(cls, field: object, value: object) -> object:
        return field == value

    @classmethod
    def _build_extra_filters(cls, **kwargs: dict[str, object]) -> list:
        """
        Build SQLAlchemy filter expressions from keyword arguments.

        Args:
            **kwargs: Filter parameters with special suffixes.

        Returns:
            List of SQLAlchemy filter expressions.

        """
        extra_filters = []
        for key, value in kwargs.items():
            if value is None:
                continue
            base_field = basic.get_base_field_name(key)
            if (
                cls.search_field_set()
                and base_field not in cls.search_field_set()
            ):
                continue
            if (
                cls.search_exclude_set()
                and base_field in cls.search_exclude_set()
            ):
                continue
            if not hasattr(cls, base_field):
                continue
            field = getattr(cls, base_field)
            if key.endswith("_from") or key.endswith("_to"):
                filt = cls._range_filter(field, key, value)
                if filt is not None:
                    extra_filters.append(filt)
            elif key.endswith("_in") or key.endswith("_nin"):
                filt = cls._in_nin_filter(field, key, value)
                if filt is not None:
                    extra_filters.append(filt)
            else:
                extra_filters.append(cls._equality_filter(field, value))
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
    ) -> list[object]:
        """Build SQLAlchemy query filters based on provided parameters."""
        base_query = []
        base_query.append(cls.is_deleted == is_deleted)
        if hasattr(cls, "user_id") and user_id:
            base_query.append(cls.user_id == user_id)  # type: ignore
        if hasattr(cls, "tenant_id") and tenant_id:
            base_query.append(cls.tenant_id == tenant_id)  # type: ignore
        if uid:
            base_query.append(cls.uid == uid)
        # Extract extra filters from kwargs
        extra_filters = cls._build_extra_filters(**kwargs)
        base_query.extend(extra_filters)
        return base_query

    @classmethod
    def get_query(
        cls,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        **kwargs: object,
    ) -> list:
        """Build query filters for database queries."""
        base_query = cls.get_queryset(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            uid=uid,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            **kwargs,
        )
        return base_query

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
        """Retrieve a single item by UID."""
        base_query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )
        base_query.append(cls.uid == uid)

        async with async_session() as session:
            query = select(cls).filter(*base_query)
            result = await session.execute(query)
            item = result.scalar_one_or_none()
        return item

    @classmethod
    async def list_items(
        cls,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        offset: int = 0,
        limit: int = 10,
        **kwargs: object,
    ) -> list[Self]:
        """List items with pagination."""
        base_query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )

        items_query = (
            select(cls)
            .filter(*base_query)
            .order_by(cls.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        async with async_session() as session:
            items_result = await session.execute(items_query)
            items = items_result.scalars().all()
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
        """Get total count of items matching filters."""
        base_query = cls.get_query(
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **kwargs,
        )

        # Query for getting the total count of items
        total_count_query = select(func.count()).filter(
            *base_query
        )  # .subquery()

        async with async_session() as session:
            total_result = await session.execute(total_count_query)
        total = total_result.scalar()

        return total

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
        """List items with pagination and return total count."""
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
    async def get_by_uid(cls, uid: str) -> Self | None:
        """Get item by UID."""
        async with async_session() as session:
            query = select(cls).filter(cls.uid == uid)
            result = await session.execute(query)
            item = result.scalar_one_or_none()
        return item

    @classmethod
    async def create_item(cls, data: dict) -> Self:
        """Create a new item."""
        item = cls(**data)
        async with async_session() as session:
            session.add(item)
            await session.commit()
            await session.refresh(item)
        return item

    @classmethod
    async def update_item(cls, item: Self, data: dict) -> Self:
        """Update an existing item."""
        for key, value in data.items():
            if cls.update_field_set() and key not in cls.update_field_set():
                continue
            if cls.update_exclude_set() and key in cls.update_exclude_set():
                continue

            setattr(item, key, value)

        async with async_session() as session:
            session.add(item)
            await session.commit()
            await session.refresh(item)
        return item

    @classmethod
    async def delete_item(cls, item: Self) -> Self:
        """Soft delete an item by setting is_deleted to True."""
        item.is_deleted = True
        async with async_session() as session:
            session.add(item)
            await session.commit()
            await session.refresh(item)
        return item


class UserOwnedEntity(BaseEntity):
    """Base entity class for user-owned SQL resources."""

    __abstract__ = True

    user_id: Mapped[str] = mapped_column(index=True)

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude during creation, including user_id."""
        return [*super().create_exclude_set(), "user_id"]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude during update, including user_id."""
        return [*super().update_exclude_set(), "user_id"]


class TenantScopedEntity(BaseEntity):
    """Base entity class for tenant-scoped SQL resources."""

    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(index=True)

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """
        Get list of fields to exclude during creation, including tenant_id.

        Returns:
            List of field names to exclude, including tenant_id.
        """
        return [*super().create_exclude_set(), "tenant_id"]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """Get list of fields to exclude during update, including tenant_id."""
        return [*super().update_exclude_set(), "tenant_id"]


class TenantUserEntity(TenantScopedEntity, UserOwnedEntity):
    """Base entity class for tenant and user scoped SQL resources."""

    __abstract__ = True

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        """
        Get list of fields to exclude during creation.

        Returns:
            List of field names to exclude, including tenant_id and user_id.
        """
        return list({*super().create_exclude_set(), "tenant_id", "user_id"})

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        """
        Get list of fields to exclude during update.

        Returns:
            List of field names to exclude, including tenant_id and user_id.
        """
        return list({*super().update_exclude_set(), "tenant_id", "user_id"})


class ImmutableMixin(BaseEntity):
    """Mixin for immutable SQL entities (cannot be updated or deleted)."""

    __abstract__ = True

    @staticmethod
    def prevent_update(
        mapper: object, connection: object, target: object
    ) -> None:
        """Prevent updates to immutable items."""
        if connection.in_transaction() and target.id is not None:
            raise ValueError("Immutable items cannot be updated")

    @classmethod
    def __declare_last__(cls) -> None:
        """Register event listener to prevent updates."""
        event.listen(cls, "before_update", cls.prevent_update)

    @classmethod
    async def update_item(cls, item: Self, data: dict) -> Never:
        """Raise error as immutable items cannot be updated."""
        raise ValueError("Immutable items cannot be updated")

    @classmethod
    async def delete_item(cls, item: Self) -> Never:
        """Raise error as immutable items cannot be deleted."""
        raise ValueError("Immutable items cannot be deleted")
