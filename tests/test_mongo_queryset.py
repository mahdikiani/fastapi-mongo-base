"""Unit tests for Mongo BaseEntity queryset scope filters."""

from __future__ import annotations

from src.fastapi_mongo_base.models import (
    BaseEntity,
    OwnedEntity,
    WorkspaceOwnedEntity,
)


class _ScopedWorkspaceEntity(WorkspaceOwnedEntity):
    """Concrete workspace entity for queryset tests."""

    class Settings(WorkspaceOwnedEntity.Settings):
        name = "test_scoped_workspace_entities"
        __abstract__ = True


class _ScopedOwnedEntity(OwnedEntity):
    """Concrete owned entity for queryset tests."""

    class Settings(OwnedEntity.Settings):
        name = "test_scoped_owned_entities"
        __abstract__ = True


class _RestrictedWorkspaceEntity(WorkspaceOwnedEntity):
    """Workspace entity that excludes workspace_id from search kwargs."""

    class Settings(WorkspaceOwnedEntity.Settings):
        name = "test_restricted_workspace_entities"
        __abstract__ = True

    @classmethod
    def search_exclude_set(cls) -> list[str]:
        return [*super().search_exclude_set(), "workspace_id"]


class _PlainEntity(BaseEntity):
    """Entity without ownership fields."""

    class Settings(BaseEntity.Settings):
        name = "test_plain_entities"
        __abstract__ = True


def test_get_queryset_applies_workspace_id() -> None:
    """workspace_id is a first-class scope filter on workspace entities."""
    qs = _ScopedWorkspaceEntity.get_queryset(workspace_id="ws-1")
    assert qs["workspace_id"] == "ws-1"
    assert qs["is_deleted"] is False


def test_get_queryset_skips_workspace_id_without_field() -> None:
    """workspace_id is ignored when the model has no such field."""
    qs = _PlainEntity.get_queryset(workspace_id="ws-1")
    assert "workspace_id" not in qs


def test_get_queryset_applies_owner_id() -> None:
    """owner_id remains a first-class scope filter."""
    qs = _ScopedOwnedEntity.get_queryset(owner_id="owner-1")
    assert qs["owner_id"] == "owner-1"


def test_workspace_id_survives_search_exclude_set() -> None:
    """First-class workspace_id is not dropped by search_exclude_set."""
    qs = _RestrictedWorkspaceEntity.get_queryset(workspace_id="ws-1")
    assert qs["workspace_id"] == "ws-1"


def test_kwargs_workspace_id_respects_search_exclude_set() -> None:
    """Kwargs path still honors search_exclude_set for workspace_id."""
    qs = _RestrictedWorkspaceEntity.get_queryset()
    # Force kwargs path: call _build_extra_filters directly
    filters = _RestrictedWorkspaceEntity._build_extra_filters(
        workspace_id="ws-1",
    )
    assert "workspace_id" not in filters
    assert qs == {"is_deleted": False}
