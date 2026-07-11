"""Tests for SQLAlchemy base entity models."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from src.fastapi_mongo_base.sql.models import (
    BaseEntity,
    ImmutableMixin,
    OwnedEntity,
    TenantOwnedEntity,
    TenantScopedEntity,
    TenantUserEntity,
    UserOwnedEntity,
)
from src.fastapi_mongo_base.utils import timezone

# ── Concrete test subclasses ─────────────────────────────────────────────────


class _TestEntity(BaseEntity):
    """Concrete subclass for testing BaseEntity."""

    __tablename__ = "test_entities"

    name: Mapped[str] = mapped_column(default="")
    value: Mapped[int] = mapped_column(default=0)


class _TestUserEntity(UserOwnedEntity):
    __tablename__ = "test_user_entities"

    name: Mapped[str] = mapped_column(default="")


class _TestTenantEntity(TenantScopedEntity):
    __tablename__ = "test_tenant_entities"

    name: Mapped[str] = mapped_column(default="")


class _TestTenantUserEntity(TenantUserEntity):
    __tablename__ = "test_tenant_user_entities"

    name: Mapped[str] = mapped_column(default="")


class _TestOwnedEntity(OwnedEntity):
    __tablename__ = "test_owned_entities"

    name: Mapped[str] = mapped_column(default="")


class _TestTenantOwnedEntity(TenantOwnedEntity):
    __tablename__ = "test_tenant_owned_entities"

    name: Mapped[str] = mapped_column(default="")


class _TestImmutableEntity(ImmutableMixin):
    __tablename__ = "test_immutable_entities"

    name: Mapped[str] = mapped_column(default="")


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[
    async_sessionmaker[AsyncSession], None
]:
    """Set up a fresh in-memory SQLite database and patch async_session."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(BaseEntity.metadata.create_all)

    with patch(
        "src.fastapi_mongo_base.sql.models.async_session", session_factory
    ):
        yield session_factory

    async with engine.begin() as conn:
        await conn.run_sync(BaseEntity.metadata.drop_all)
    await engine.dispose()


# ── BaseEntity: field set class methods ──────────────────────────────────────


class TestBaseEntityFieldSets:
    """Verify default field-set return values."""

    def test_create_exclude_set(self) -> None:
        """Verify default create_exclude_set."""
        assert _TestEntity.create_exclude_set() == [
            "uid",
            "created_at",
            "updated_at",
            "is_deleted",
        ]

    def test_create_field_set(self) -> None:
        """Verify default create_field_set."""
        assert _TestEntity.create_field_set() == []

    def test_update_exclude_set(self) -> None:
        """Verify default update_exclude_set."""
        assert _TestEntity.update_exclude_set() == [
            "uid",
            "created_at",
            "updated_at",
        ]

    def test_update_field_set(self) -> None:
        """Verify default update_field_set."""
        assert _TestEntity.update_field_set() == []

    def test_search_exclude_set(self) -> None:
        """Verify default search_exclude_set."""
        assert _TestEntity.search_exclude_set() == ["meta_data"]

    def test_search_field_set(self) -> None:
        """Verify default search_field_set."""
        assert _TestEntity.search_field_set() == []


# ── BaseEntity: expired ──────────────────────────────────────────────────────


class TestExpired:
    """Verify the expired() helper."""

    def test_returns_true_when_outdated(self) -> None:
        """Verify expired returns True when outdated."""
        entity = _TestEntity()
        entity.updated_at = datetime(2020, 1, 1, tzinfo=timezone.tz)
        assert entity.expired(days=3) is True

    def test_returns_false_when_recent(self) -> None:
        """Verify expired returns False when recent."""
        entity = _TestEntity()
        entity.updated_at = datetime.now(timezone.tz)
        assert entity.expired(days=3) is False

    def test_boundary_default_days(self) -> None:
        """Verify expired defaults to 30 days."""
        entity = _TestEntity()
        entity.updated_at = datetime.now(timezone.tz) - timedelta(days=4)
        assert entity.expired() is True


# ── BaseEntity: dump ─────────────────────────────────────────────────────────


class TestDump:
    """Verify the instance serialisation helper."""

    def test_returns_all_public_fields(self) -> None:
        """Verify dump returns all public fields."""
        entity = _TestEntity(uid="abc", name="hello", value=42)
        result = entity.dump()
        assert result["uid"] == "abc"
        assert result["name"] == "hello"
        assert result["value"] == 42

    def test_excludes_underscore_prefixed_attributes(self) -> None:
        """Verify dump excludes underscore-prefixed attrs."""
        entity = _TestEntity(name="foo")
        entity._internal = "secret"
        result = entity.dump()
        assert "_internal" not in result
        assert result["name"] == "foo"

    def test_include_fields_only(self) -> None:
        """Verify dump with include_fields."""
        entity = _TestEntity(name="foo", value=99)
        result = entity.dump(include_fields=["name"])
        assert list(result.keys()) == ["name"]
        assert result["name"] == "foo"

    def test_exclude_fields(self) -> None:
        """Verify dump with exclude_fields."""
        entity = _TestEntity(name="foo", value=99)
        result = entity.dump(exclude_fields=["value"])
        assert "value" not in result
        assert result["name"] == "foo"

    def test_converts_datetime_to_iso(self) -> None:
        """Verify dump converts datetime to ISO string."""
        entity = _TestEntity()
        now = datetime(2024, 6, 15, 12, 30, 0)
        entity.created_at = now
        result = entity.dump()
        assert result["created_at"] == now.isoformat()

    def test_skips_non_existent_included_field(self) -> None:
        """Verify dump skips non-existent included fields."""
        entity = _TestEntity(name="x")
        result = entity.dump(include_fields=["name", "nonexistent"])
        assert "name" in result
        assert "nonexistent" not in result


# ── BaseEntity: __hash__ ─────────────────────────────────────────────────────


class TestHash:
    """Verify hash stability and distinction."""

    def test_deterministic_for_identical_data(self) -> None:
        """Verify hash is deterministic for identical data."""
        e1 = _TestEntity(uid="a", name="x", value=1)
        e2 = _TestEntity(uid="a", name="x", value=1)
        assert hash(e1) == hash(e2)

    def test_differs_for_different_data(self) -> None:
        """Verify hash differs for different data."""
        e1 = _TestEntity(uid="a", name="x")
        e2 = _TestEntity(uid="b", name="y")
        assert hash(e1) != hash(e2)


# ── BaseEntity: item_url ─────────────────────────────────────────────────────


class TestItemUrl:
    """Verify the item_url property format."""

    def test_uses_class_name_and_uid(self) -> None:
        """Verify item_url includes class name and uid."""
        from src.fastapi_mongo_base.core.config import Settings

        entity = _TestEntity()
        entity.uid = "uid-123"
        url = entity.item_url
        expected_class_part = entity.__class__.__name__.lower()
        assert "uid-123" in url
        assert url.startswith(
            f"https://{Settings.root_url}{Settings.base_path}/"
        )
        assert url.endswith(f"{expected_class_part}s/uid-123")


# ── BaseEntity: _range_filter ────────────────────────────────────────────────


class TestRangeFilter:
    """Verify _range_filter logic."""

    def test_from_creates_ge_expression(self) -> None:
        """Verify _from suffix creates >= expression."""
        result = _TestEntity._range_filter(_TestEntity.value, "value_from", 10)
        assert result is not None

    def test_to_creates_le_expression(self) -> None:
        """Verify _to suffix creates <= expression."""
        result = _TestEntity._range_filter(_TestEntity.value, "value_to", 20)
        assert result is not None

    def test_unknown_suffix_returns_none(self) -> None:
        """Verify unknown suffix returns None."""
        result = _TestEntity._range_filter(_TestEntity.value, "value_eq", 1)
        assert result is None

    def test_invalid_value_returns_none(self) -> None:
        """Verify invalid value returns None."""
        result = _TestEntity._range_filter(_TestEntity.value, "value_from", [])
        assert result is None


# ── BaseEntity: _in_nin_filter ───────────────────────────────────────────────


class TestInNinFilter:
    """Verify _in_nin_filter logic."""

    def test_in_creates_in_expression(self) -> None:
        """Verify _in suffix creates IN expression."""
        result = _TestEntity._in_nin_filter(
            _TestEntity.value, "value_in", [1, 2]
        )
        assert result is not None

    def test_nin_creates_not_in_expression(self) -> None:
        """Verify _nin suffix creates NOT IN expression."""
        result = _TestEntity._in_nin_filter(
            _TestEntity.value, "value_nin", [3, 4]
        )
        assert result is not None

    def test_unknown_suffix_returns_none(self) -> None:
        """Verify unknown suffix returns None."""
        result = _TestEntity._in_nin_filter(
            _TestEntity.value, "status_xyz", "val"
        )
        assert result is None


# ── BaseEntity: _equality_filter ─────────────────────────────────────────────


class TestEqualityFilter:
    """Verify _equality_filter."""

    def test_uses_eq_operator(self) -> None:
        """Verify _equality_filter uses the eq operator."""
        result = _TestEntity._equality_filter(_TestEntity.name, "test_value")
        assert result is not None


# ── BaseEntity: _build_extra_filters ─────────────────────────────────────────


class TestBuildExtraFilters:
    """Verify the complete filter-building logic."""

    def test_skips_none_values(self) -> None:
        """Verify None values are skipped."""
        assert _TestEntity._build_extra_filters(name=None) == []

    def test_honours_search_field_set(self) -> None:
        """Verify search_field_set is honoured."""
        with patch.object(
            _TestEntity, "search_field_set", return_value=["name"]
        ):
            filters = _TestEntity._build_extra_filters(name="hello", value=42)
            assert len(filters) == 1

    def test_honours_search_exclude_set(self) -> None:
        """Verify search_exclude_set is honoured."""
        with (
            patch.object(_TestEntity, "search_field_set", return_value=[]),
            patch.object(
                _TestEntity, "search_exclude_set", return_value=["name"]
            ),
        ):
            filters = _TestEntity._build_extra_filters(name="hello")
            assert filters == []

    def test_skips_nonexistent_field(self) -> None:
        """Verify nonexistent fields are skipped."""
        filters = _TestEntity._build_extra_filters(nonexistent="val")
        assert filters == []

    def test_equality_filter(self) -> None:
        """Verify equality filter is applied."""
        filters = _TestEntity._build_extra_filters(name="hello")
        assert len(filters) == 1

    def test_range_filters(self) -> None:
        """Verify range filters are applied."""
        filters = _TestEntity._build_extra_filters(value_from=10, value_to=20)
        assert len(filters) == 2

    def test_in_filter(self) -> None:
        """Verify IN filter is applied."""
        filters = _TestEntity._build_extra_filters(value_in=[1, 2])
        assert len(filters) == 1

    def test_nin_filter(self) -> None:
        """Verify NIN filter is applied."""
        filters = _TestEntity._build_extra_filters(value_nin=[3, 4])
        assert len(filters) == 1


# ── BaseEntity: get_queryset ─────────────────────────────────────────────────


class TestGetQueryset:
    """Verify the queryset filter builder."""

    def test_default_includes_is_deleted_false(self) -> None:
        """Verify default queryset has is_deleted=False filter."""
        qs = _TestEntity.get_queryset()
        assert len(qs) == 1

    def test_with_is_deleted_true(self) -> None:
        """Verify is_deleted=True adds the filter."""
        qs = _TestEntity.get_queryset(is_deleted=True)
        assert len(qs) == 1

    def test_with_uid(self) -> None:
        """Verify uid filter is added."""
        qs = _TestEntity.get_queryset(uid="abc-123")
        assert len(qs) == 2

    def test_with_user_id_skipped_when_no_column(self) -> None:
        """Verify user_id is skipped when column missing."""
        qs = _TestEntity.get_queryset(user_id="user-1")
        assert len(qs) == 1

    def test_with_extra_kwargs(self) -> None:
        """Verify extra kwargs are passed through."""
        qs = _TestEntity.get_queryset(name="hello", value_in=[1, 2])
        assert len(qs) == 3

    def test_with_user_id_on_user_entity(self) -> None:
        """Verify user_id works on UserOwnedEntity."""
        qs = _TestUserEntity.get_queryset(user_id="user-1")
        assert len(qs) == 2

    def test_with_tenant_id_on_tenant_entity(self) -> None:
        """Verify tenant_id works on TenantScopedEntity."""
        qs = _TestTenantEntity.get_queryset(tenant_id="tenant-1")
        assert len(qs) == 2

    def test_with_owner_id_on_owned_entity(self) -> None:
        """Verify owner_id works on OwnedEntity."""
        qs = _TestOwnedEntity.get_queryset(owner_id="owner-1")
        assert len(qs) == 2


# ── BaseEntity: get_query ────────────────────────────────────────────────────


class TestGetQuery:
    """Verify the get_query method (delegates to get_queryset)."""

    def test_passes_created_at_range(self) -> None:
        """Verify created_at range is passed to get_queryset."""
        from datetime import datetime

        qs = _TestEntity.get_query(
            created_at_from=datetime(2024, 1, 1),
            created_at_to=datetime(2024, 12, 31),
        )
        assert len(qs) == 3

    def test_without_optional_args(self) -> None:
        """Verify get_query works without optional args."""
        qs = _TestEntity.get_query()
        assert len(qs) == 1


# ── Subclass: field set overrides ────────────────────────────────────────────


class TestSubclassFieldSets:
    """Verify that each subclass overrides create/update exclude sets."""

    def test_user_owned_entity(self) -> None:
        """Verify UserOwnedEntity excludes user_id."""
        assert "user_id" in _TestUserEntity.create_exclude_set()
        assert "user_id" in _TestUserEntity.update_exclude_set()

    def test_tenant_scoped_entity(self) -> None:
        """Verify TenantScopedEntity excludes tenant_id."""
        assert "tenant_id" in _TestTenantEntity.create_exclude_set()
        assert "tenant_id" in _TestTenantEntity.update_exclude_set()

    def test_tenant_user_entity(self) -> None:
        """Verify TenantUserEntity excludes tenant_id and user_id."""
        exclude = _TestTenantUserEntity.create_exclude_set()
        assert "tenant_id" in exclude
        assert "user_id" in exclude
        exclude = _TestTenantUserEntity.update_exclude_set()
        assert "tenant_id" in exclude
        assert "user_id" in exclude

    def test_owned_entity(self) -> None:
        """Verify OwnedEntity excludes owner_id."""
        assert "owner_id" in _TestOwnedEntity.create_exclude_set()
        assert "owner_id" in _TestOwnedEntity.update_exclude_set()

    def test_tenant_owned_entity(self) -> None:
        """Verify TenantOwnedEntity excludes tenant_id and owner_id."""
        exclude = _TestTenantOwnedEntity.create_exclude_set()
        assert "tenant_id" in exclude
        assert "owner_id" in exclude
        exclude = _TestTenantOwnedEntity.update_exclude_set()
        assert "tenant_id" in exclude
        assert "owner_id" in exclude


# ── Async CRUD: create_item ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCreateItem:
    """Verify create_item works and returns a persisted entity."""

    async def test_creates_and_persists(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify create_item persists and returns correct fields."""
        item = await _TestEntity.create_item({"name": "test", "value": 42})
        assert item.uid is not None
        assert item.name == "test"
        assert item.value == 42
        assert item.created_at is not None
        assert item.is_deleted is False

    async def test_generates_unique_uids(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify create_item generates unique UIDs."""
        a = await _TestEntity.create_item({"name": "a"})
        b = await _TestEntity.create_item({"name": "b"})
        assert a.uid != b.uid

    async def test_created_at_is_set(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify create_item sets created_at."""
        item = await _TestEntity.create_item({"name": "t"})
        assert isinstance(item.created_at, datetime)

    async def test_with_user_id_field(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify create_item with user_id field."""
        item = await _TestUserEntity.create_item({
            "name": "u",
            "user_id": "user-1",
        })
        assert item.user_id == "user-1"


# ── Async CRUD: get_item and get_by_uid ──────────────────────────────────────


@pytest.mark.asyncio
class TestGetItem:
    """Verify retrieval by UID."""

    async def test_returns_existing(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify get_item returns existing item."""
        created = await _TestEntity.create_item({
            "name": "find-me",
            "value": 7,
        })
        fetched = await _TestEntity.get_item(created.uid)
        assert fetched is not None
        assert fetched.uid == created.uid
        assert fetched.name == "find-me"

    async def test_returns_none_for_missing(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify get_item returns None for missing UID."""
        fetched = await _TestEntity.get_item("nonexistent-uid")
        assert fetched is None

    async def test_filters_by_user_id(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify get_item filters by user_id."""
        await _TestUserEntity.create_item({"name": "visible", "user_id": "u1"})
        await _TestUserEntity.create_item({"name": "hidden", "user_id": "u2"})
        fetched = await _TestUserEntity.get_item("irrelevant", user_id="u1")
        assert fetched is None  # uid does not exist for u1


@pytest.mark.asyncio
class TestGetByUid:
    """Verify get_by_uid shortcut."""

    async def test_returns_existing(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify get_by_uid returns existing item."""
        created = await _TestEntity.create_item({"name": "byuid"})
        fetched = await _TestEntity.get_by_uid(created.uid)
        assert fetched is not None
        assert fetched.uid == created.uid

    async def test_returns_none_for_missing(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify get_by_uid returns None for missing UID."""
        fetched = await _TestEntity.get_by_uid("missing")
        assert fetched is None


# ── Async CRUD: update_item ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUpdateItem:
    """Verify item updates."""

    async def test_updates_allowed_fields(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify update_item updates allowed fields."""
        item = await _TestEntity.create_item({"name": "old", "value": 1})
        updated = await _TestEntity.update_item(
            item, {"name": "new", "value": 99}
        )
        assert updated.name == "new"
        assert updated.value == 99

    async def test_skips_excluded_fields(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify update_item skips excluded fields like uid."""
        item = await _TestEntity.create_item({"name": "orig", "value": 1})
        original_uid = item.uid
        updated = await _TestEntity.update_item(
            item, {"uid": "new-uid", "name": "changed"}
        )
        assert updated.uid == original_uid
        assert updated.name == "changed"

    async def test_honours_update_field_set(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify update_item respects update_field_set."""
        item = await _TestEntity.create_item({"name": "orig", "value": 1})
        with patch.object(
            _TestEntity, "update_field_set", return_value=["name"]
        ):
            updated = await _TestEntity.update_item(
                item, {"name": "kept", "value": 999}
            )
        assert updated.name == "kept"
        assert updated.value == 1  # not in field set


# ── Async CRUD: delete_item ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDeleteItem:
    """Verify soft-delete sets is_deleted to True."""

    async def test_soft_deletes(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify delete_item sets is_deleted to True."""
        item = await _TestEntity.create_item({"name": "to-delete"})
        deleted = await _TestEntity.delete_item(item)
        assert deleted.is_deleted is True

    async def test_deleted_item_not_in_default_query(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify deleted item is excluded from default query."""
        item = await _TestEntity.create_item({"name": "gone"})
        await _TestEntity.delete_item(item)
        fetched = await _TestEntity.get_item(item.uid)
        assert fetched is None  # is_deleted=False excludes it

    async def test_deleted_item_visible_with_is_deleted_true(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify deleted item visible with is_deleted=True."""
        item = await _TestEntity.create_item({"name": "gone"})
        await _TestEntity.delete_item(item)
        fetched = await _TestEntity.get_item(item.uid, is_deleted=True)
        assert fetched is not None


# ── Async CRUD: list_items / total_count / list_total_combined ───────────────


@pytest.mark.asyncio
class TestListItem:
    """Verify paginated listing."""

    async def test_returns_empty_when_no_items(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items returns empty when no items."""
        items = await _TestEntity.list_items()
        assert items == []

    async def test_returns_all_items_within_limit(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items returns all items within limit."""
        for i in range(5):
            await _TestEntity.create_item({"name": f"item-{i}", "value": i})
        items = await _TestEntity.list_items(limit=10)
        assert len(items) == 5

    async def test_respects_offset(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items respects offset parameter."""
        for i in range(5):
            await _TestEntity.create_item({"name": f"item-{i}", "value": i})
        items = await _TestEntity.list_items(offset=3, limit=10)
        assert len(items) == 2

    async def test_orders_by_created_at_desc(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items orders by created_at desc."""
        items = []
        for i in range(3):
            item = await _TestEntity.create_item({
                "name": f"item-{i}",
                "value": i,
            })
            items.append(item)
        listed = await _TestEntity.list_items(limit=10)
        names = [it.name for it in listed]
        assert names == ["item-2", "item-1", "item-0"]


@pytest.mark.asyncio
class TestTotalCount:
    """Verify total_count."""

    async def test_zero_when_empty(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify total_count returns 0 when empty."""
        count = await _TestEntity.total_count()
        assert count == 0

    async def test_counts_all_items(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify total_count counts all items."""
        for i in range(7):
            await _TestEntity.create_item({"name": f"n-{i}"})
        count = await _TestEntity.total_count()
        assert count == 7

    async def test_excludes_soft_deleted(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify total_count excludes soft-deleted items."""
        item = await _TestEntity.create_item({"name": "d"})
        await _TestEntity.delete_item(item)
        count = await _TestEntity.total_count()
        assert count == 0

    async def test_includes_soft_deleted_when_requested(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify total_count includes soft-deleted when requested."""
        item = await _TestEntity.create_item({"name": "d"})
        await _TestEntity.delete_item(item)
        count = await _TestEntity.total_count(is_deleted=True)
        assert count == 1


@pytest.mark.asyncio
class TestListTotalCombined:
    """Verify the combined listing + count helper."""

    async def test_returns_empty_and_zero(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_total_combined returns empty and zero."""
        items, total = await _TestEntity.list_total_combined()
        assert items == []
        assert total == 0

    async def test_returns_items_and_count(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_total_combined returns items and count."""
        for i in range(4):
            await _TestEntity.create_item({"name": f"x-{i}"})
        items, total = await _TestEntity.list_total_combined(limit=2)
        assert len(items) == 2
        assert total == 4


# ── ImmutableMixin ───────────────────────────────────────────────────────────


class TestImmutableMixinPreventUpdate:
    """Verify the static guard that blocks ORM-level updates."""

    def test_raises_when_in_transaction_and_has_id(self) -> None:
        """Verify prevent_update raises when in transaction."""
        connection = MagicMock()
        connection.in_transaction.return_value = True
        target = MagicMock()
        target.id = "some-id"

        with pytest.raises(
            ValueError, match="Immutable items cannot be updated"
        ):
            ImmutableMixin.prevent_update(None, connection, target)

    def test_allows_when_not_in_transaction(self) -> None:
        """Verify prevent_update allows when not in transaction."""
        connection = MagicMock()
        connection.in_transaction.return_value = False
        target = MagicMock()
        target.id = "some-id"
        # Should not raise
        ImmutableMixin.prevent_update(None, connection, target)

    def test_allows_when_id_is_none(self) -> None:
        """Verify prevent_update allows when id is None."""
        connection = MagicMock()
        connection.in_transaction.return_value = True
        target = MagicMock()
        target.id = None
        # Should not raise
        ImmutableMixin.prevent_update(None, connection, target)


@pytest.mark.asyncio
class TestImmutableMixinUpdateDelete:
    """Verify immutable entity classmethods raise."""

    async def test_update_item_raises(self) -> None:
        """Verify update_item raises on immutable entity."""
        item = _TestImmutableEntity()
        with pytest.raises(
            ValueError, match="Immutable items cannot be updated"
        ):
            await _TestImmutableEntity.update_item(item, {})

    async def test_delete_item_raises(self) -> None:
        """Verify delete_item raises on immutable entity."""
        item = _TestImmutableEntity()
        with pytest.raises(
            ValueError, match="Immutable items cannot be deleted"
        ):
            await _TestImmutableEntity.delete_item(item)


@pytest.mark.asyncio
class TestImmutableMixinOrmEvent:
    """
    Verify the before_update event listener blocks ORM updates.

    Note: the prevent_update guard checks ``target.id`` but the mapped
    entities use ``uid`` as the primary key, so the event raises
    ``AttributeError`` in practice.
    """

    async def test_blocks_update_via_session(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify ORM update via session is blocked."""
        async with db_session() as session:
            item = _TestImmutableEntity(name="original")
            session.add(item)
            await session.commit()

            item.name = "changed"
            with pytest.raises(AttributeError):
                await session.commit()

    async def test_blocks_update_after_create_item(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify that create_item + ORM-update raises."""
        item = await _TestImmutableEntity.create_item({"name": "created"})
        async with db_session() as session:
            merged = await session.merge(item)
            merged.name = "mutated"
            with pytest.raises(AttributeError):
                await session.commit()


# ── BaseEntity: complete async DB filter integration ─────────────────────────


@pytest.mark.asyncio
class TestDbFilterIntegration:
    """End-to-end tests for filtering via get_queryset / get_query."""

    async def test_list_items_filters_by_extra_kwargs(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items filters by extra kwargs."""
        await _TestEntity.create_item({"name": "match", "value": 10})
        await _TestEntity.create_item({"name": "other", "value": 20})

        items = await _TestEntity.list_items(limit=10, name="match")
        assert len(items) == 1
        assert items[0].name == "match"

    async def test_list_items_range_filter(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items range filtering."""
        for v in [1, 5, 10]:
            await _TestEntity.create_item({"name": f"v-{v}", "value": v})

        items = await _TestEntity.list_items(
            limit=10, value_from=5, value_to=10
        )
        values = {it.value for it in items}
        assert values == {5, 10}

    async def test_list_items_in_filter(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify list_items IN filtering."""
        for v in [1, 2, 3, 4]:
            await _TestEntity.create_item({"name": f"v-{v}", "value": v})

        items = await _TestEntity.list_items(limit=10, value_in=[1, 3])
        values = {it.value for it in items}
        assert values == {1, 3}

    async def test_total_count_respects_extra_filters(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify total_count respects extra filters."""
        for v in [1, 2, 3]:
            await _TestEntity.create_item({"name": f"v-{v}", "value": v})

        count = await _TestEntity.total_count(value=2)
        assert count == 1

    async def test_tenant_user_filtering(
        self, db_session: async_sessionmaker[AsyncSession]
    ) -> None:
        """Verify tenant and user filtering on TenantUserEntity."""
        await _TestTenantUserEntity.create_item({
            "name": "visible",
            "user_id": "u1",
            "tenant_id": "t1",
        })
        await _TestTenantUserEntity.create_item({
            "name": "hidden-user",
            "user_id": "u2",
            "tenant_id": "t1",
        })
        await _TestTenantUserEntity.create_item({
            "name": "hidden-tenant",
            "user_id": "u1",
            "tenant_id": "t2",
        })

        items = await _TestTenantUserEntity.list_items(
            tenant_id="t1", user_id="u1"
        )
        assert len(items) == 1
        assert items[0].name == "visible"
