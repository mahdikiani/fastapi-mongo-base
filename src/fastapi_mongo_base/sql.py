import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, event, select
from sqlalchemy.orm import Mapped, as_declarative, declared_attr, mapped_column
from sqlalchemy.sql import func

from .core.config import Settings
from .utils import basic, timezone

async_session = None


@as_declarative()
class BaseEntity:
    id: Any
    __name__: str
    __abstract__ = True

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    uid: Mapped[str] = mapped_column(
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.tz),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.tz), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(default=False)
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

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

    def dump(
        self,
        include_fields: list[str] = None,
        exclude_fields: list[str] = None,
    ) -> dict:
        """
        Dump the object into a dictionary.
        It includes all the fields of the object.
        """
        result = {}
        for key, value in (include_fields or self.__dict__).items():
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

    def __hash__(self):
        json_str = json.dumps(self.dump())
        return hash(json_str)

    @property
    def item_url(self):
        return "/".join([
            f"https://{Settings.root_url}{Settings.base_path}",
            f"{self.__class__.__name__.lower()}s",
            f"{self.uid}",
        ])

    @classmethod
    def get_queryset(
        cls,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        uid: str | None = None,
        *args,
        **kwargs,
    ) -> list:
        """Build SQLAlchemy query filters based on provided parameters.

        Args:
            user_id: Filter by user ID if the model has user_id field
            tenant_id: Filter by tenant ID if the model has tenant_id field
            is_deleted: Filter by deletion status
            uid: Filter by unique identifier
            **kwargs: Additional filters that can include range queries
                      with _from/_to suffixes

        Returns:
            List of SQLAlchemy query conditions
        """
        # Start with basic filters
        base_query = []

        # Add standard filters if applicable
        base_query.append(cls.is_deleted == is_deleted)

        if hasattr(cls, "user_id") and user_id:
            base_query.append(cls.user_id == user_id)

        if hasattr(cls, "tenant_id") and tenant_id:
            base_query.append(cls.tenant_id == tenant_id)

        if uid:
            base_query.append(cls.uid == uid)

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

            field = getattr(cls, base_field)

            # Handle range queries and array operators
            if key.endswith("_from") or key.endswith("_to"):
                if basic.is_valid_range_value(value):
                    if key.endswith("_from"):
                        base_query.append(field >= value)
                    elif key.endswith("_to"):
                        base_query.append(field <= value)
            elif key.endswith("_in") or key.endswith("_nin"):
                value_list = basic.parse_array_parameter(value)
                if key.endswith("_in"):
                    base_query.append(field.in_(value_list))
                else:  # _nin
                    base_query.append(~field.in_(value_list))
            else:
                base_query.append(field == value)

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
        **kwargs,
    ):
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
        *,
        uid: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs,
    ):
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
        **kwargs,
    ):
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
        **kwargs,
    ):
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
        async with async_session() as session:
            query = select(cls).filter(cls.uid == uid)
            result = await session.execute(query)
            item = result.scalar_one_or_none()
        return item

    @classmethod
    async def create_item(cls, data: dict):
        item = cls(**data)
        async with async_session() as session:
            session.add(item)
            await session.commit()
            await session.refresh(item)
        return item

    @classmethod
    async def update_item(cls, item: "BaseEntity", data: dict):
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
    async def delete_item(cls, item: "BaseEntity"):
        item.is_deleted = True
        async with async_session() as session:
            session.add(item)
            await session.commit()
            await session.refresh(item)
        return item


class UserOwnedEntity(BaseEntity):
    __abstract__ = True

    user_id: Mapped[str] = mapped_column(index=True)

    @classmethod
    def create_exclude_set(cls) -> list:
        return super().create_exclude_set() + ["user_id"]

    @classmethod
    def update_exclude_set(cls) -> list:
        return super().update_exclude_set() + ["user_id"]


class TenantScopedEntity(BaseEntity):
    __abstract__ = True

    tenant_id: Mapped[str] = mapped_column(index=True)

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return super().create_exclude_set() + ["tenant_id"]

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return super().update_exclude_set() + ["tenant_id"]


class TenantUserEntity(TenantScopedEntity, UserOwnedEntity):
    __abstract__ = True

    @classmethod
    def create_exclude_set(cls) -> list[str]:
        return list(
            set(super().create_exclude_set() + ["tenant_id", "user_id"])
        )

    @classmethod
    def update_exclude_set(cls) -> list[str]:
        return list(
            set(super().update_exclude_set() + ["tenant_id", "user_id"])
        )


class ImmutableMixin(BaseEntity):
    __abstract__ = True

    @staticmethod
    def prevent_update(mapper, connection, target):
        if connection.in_transaction() and target.id is not None:
            raise ValueError("Immutable items cannot be updated")

    @classmethod
    def __declare_last__(cls):
        event.listen(cls, "before_update", cls.prevent_update)

    @classmethod
    async def update_item(cls, item: "BaseEntity", data: dict):
        raise ValueError("Immutable items cannot be updated")

    @classmethod
    async def delete_item(cls, item: "BaseEntity"):
        raise ValueError("Immutable items cannot be deleted")
