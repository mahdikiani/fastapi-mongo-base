"""Coverage for AbstractBaseRouter, TaskRouter, and owned entity get_item."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, Request
from pydantic import BaseModel

from fastapi_mongo_base.errors.base import BaseHTTPException
from fastapi_mongo_base.models import (
    BaseEntity,
    ImmutableMixin,
    OwnedEntity,
    TenantOwnedEntity,
    TenantScopedEntity,
    TenantUserEntity,
    TenantWorkspaceEntity,
    UserOwnedEntity,
    WorkspaceOwnedEntity,
)
from fastapi_mongo_base.routes import (
    AbstractBaseRouter,
    AbstractTaskRouter,
    copy_router,
)
from fastapi_mongo_base.schemas import BaseEntitySchema
from fastapi_mongo_base.tasks import TaskMixin
from tests.app.server import TestEntity, TestEntitySchema, TestRouter


def _request(query: str = "") -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": query.encode(),
        "client": ("test", 50000),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    })


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_router_get_item_not_found() -> None:
    """get_item raises 404 when missing."""
    router = TestRouter()
    with pytest.raises(BaseHTTPException) as exc:
        await router.get_item(uid="missing-uid-xyz")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_router_user_dependency_sync_and_async() -> None:
    """get_user covers sync/async dependency and get_user_id."""
    router = TestRouter()
    assert await router.get_user(_request()) is None
    assert await router.get_user_id(_request()) is None

    router.user_dependency = lambda _request: SimpleNamespace(uid="u-1")
    user = await router.get_user(_request())
    assert user.uid == "u-1"
    assert await router.get_user_id(_request()) == "u-1"

    async def _async_dep(_request: Request) -> SimpleNamespace:
        await asyncio.sleep(0)
        return SimpleNamespace(uid="u-2")

    router.user_dependency = _async_dep
    assert (await router.get_user(_request())).uid == "u-2"


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_router_statistics_and_create_update_with_models() -> None:
    """statistics, create/update with BaseModel payloads."""
    router = TestRouter()
    request = _request("is_deleted=false&name=x")
    stats = await router.statistics(request)
    assert "total" in stats

    class _Payload(BaseModel):
        name: str
        number: int = 1

    created = await router.create_item(
        _request(),
        _Payload(name="from-model"),
    )
    assert created.name == "from-model"

    updated = await router.update_item(
        _request(),
        created.uid,
        _Payload(name="patched"),
    )
    assert updated.name == "patched"


def test_router_schema_required_and_extra_routes() -> None:
    """Constructor schema validation and mine/statistics route flags."""

    class _SchemaOnly(AbstractBaseRouter):
        model = TestEntity
        schema = None

    with pytest.raises(ValueError, match="schema is required"):
        _SchemaOnly()

    class _ExtraRoutes(AbstractBaseRouter):
        model = TestEntity
        schema = TestEntitySchema

    router = _ExtraRoutes(
        prefix="/extra",
        tags=["Extra"],
        mine_route=True,
        statistics_route=True,
    )
    paths = {getattr(r, "path", "") for r in router.router.routes}
    assert any(p.endswith("/mine") for p in paths)
    assert any("statistics" in p for p in paths)


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_mine_items_branches() -> None:
    """mine_items create-if-missing and unique_per_user paths."""
    router = TestRouter()
    router.user_dependency = lambda _request: SimpleNamespace(uid="mine-user")
    router.create_mine_if_not_found = True
    router.unique_per_user = False
    with (
        patch.object(
            router,
            "_list_items",
            new=AsyncMock(
                return_value=SimpleNamespace(total=0, items=[]),
            ),
        ),
        patch.object(
            TestEntity,
            "create_item",
            new=AsyncMock(return_value=SimpleNamespace(uid="new")),
        ),
    ):
        resp = await router.mine_items(_request())
        assert resp.total == 1

    router.unique_per_user = True
    item = SimpleNamespace(uid="only")
    with patch.object(
        router,
        "_list_items",
        new=AsyncMock(
            return_value=SimpleNamespace(total=1, items=[item]),
        ),
    ):
        assert await router.mine_items(_request()) is item


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_task_router_methods() -> None:
    """AbstractTaskRouter start/webhook/create processing branches."""

    class _TaskSchema(BaseEntitySchema):
        name: str = "t"

    class _TaskModel(_TaskSchema, TaskMixin, BaseEntity):
        class Settings(BaseEntity.Settings):
            name = "coverage_task_entities"
            __abstract__ = True

    class _TaskRouter(AbstractTaskRouter):
        model = _TaskModel
        schema = _TaskSchema

    router = _TaskRouter(draftable=True, prefix="/tasks-cov")
    paths = {getattr(r, "path", "") for r in router.router.routes}
    assert any(p.endswith("/start") for p in paths)
    assert any(p.endswith("/webhook") for p in paths)

    stats = await router.statistics(_request())
    assert "total" in stats

    webhook = await router.webhook(_request(), "uid-1", {"ok": True})
    assert webhook["ok"] is True

    item = MagicMock()
    item.task_status = "init"
    item.start_processing = AsyncMock()
    item.model_dump.return_value = {"uid": "uid-1"}

    with patch.object(
        AbstractBaseRouter,
        "create_item",
        new=AsyncMock(return_value=item),
    ):
        bg = BackgroundTasks()
        created = await router._create_task_item(
            _request(),
            {"name": "x"},
            background_tasks=bg,
            blocking=False,
        )
        assert created is item
        assert len(bg.tasks) == 1

        await router._create_task_item(
            _request(),
            {"name": "y"},
            background_tasks=BackgroundTasks(),
            blocking=True,
        )
        item.start_processing.assert_awaited()

    class _NonDraftRouter(AbstractTaskRouter):
        model = _TaskModel
        schema = _TaskSchema

    router_nd = _NonDraftRouter(draftable=False, prefix="/tasks-nd")
    data: dict = {"name": "z"}
    with patch.object(
        AbstractBaseRouter,
        "create_item",
        new=AsyncMock(return_value=item),
    ):
        await router_nd._create_task_item(
            _request(),
            data,
            background_tasks=BackgroundTasks(),
            blocking=True,
        )
        assert data["task_status"] == "init"

    with (
        patch.object(router, "get_user_id", new=AsyncMock(return_value=None)),
        patch.object(router, "get_item", new=AsyncMock(return_value=item)),
    ):
        bg2 = BackgroundTasks()
        dumped = await router.start_item(_request(), "uid-1", bg2)
        assert dumped["uid"] == "uid-1"
        assert len(bg2.tasks) == 1


def test_copy_router_duplicates_routes() -> None:
    """copy_router clones routes under a new prefix."""
    router = TestRouter().router
    copied = copy_router(router, "/copied")
    assert copied.prefix == "/copied"
    assert len(copied.routes) == len(router.routes)


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_owned_entity_get_item_requires_ids() -> None:
    """Ownership mixins require scoped ids unless ignore flags are set."""

    class _UserEnt(UserOwnedEntity):
        class Settings(UserOwnedEntity.Settings):
            name = "cov_user_owned"
            __abstract__ = True

    class _Owned(OwnedEntity):
        class Settings(OwnedEntity.Settings):
            name = "cov_owned"
            __abstract__ = True

    class _Workspace(WorkspaceOwnedEntity):
        class Settings(WorkspaceOwnedEntity.Settings):
            name = "cov_workspace"
            __abstract__ = True

    class _Tenant(TenantScopedEntity):
        class Settings(TenantScopedEntity.Settings):
            name = "cov_tenant"
            __abstract__ = True

    class _TenantUser(TenantUserEntity):
        class Settings(TenantUserEntity.Settings):
            name = "cov_tenant_user"
            __abstract__ = True

    class _TenantWs(TenantWorkspaceEntity):
        class Settings(TenantWorkspaceEntity.Settings):
            name = "cov_tenant_ws"
            __abstract__ = True

    class _TenantOwned(TenantOwnedEntity):
        class Settings(TenantOwnedEntity.Settings):
            name = "cov_tenant_owned"
            __abstract__ = True

    with pytest.raises(ValueError, match="user_id"):
        await _UserEnt.get_item("u1")
    with pytest.raises(ValueError, match="owner_id"):
        await _Owned.get_item("u1")
    with pytest.raises(ValueError, match="workspace_id"):
        await _Workspace.get_item("u1")
    with pytest.raises(ValueError, match="tenant_id"):
        await _Tenant.get_item("u1")
    with pytest.raises(ValueError, match="tenant_id"):
        await _TenantUser.get_item("u1", user_id="u")
    with pytest.raises(ValueError, match="user_id"):
        await _TenantUser.get_item("u1", tenant_id="t")
    with pytest.raises(ValueError, match="tenant_id"):
        await _TenantWs.get_item("u1", workspace_id="w")
    with pytest.raises(ValueError, match="workspace_id"):
        await _TenantWs.get_item("u1", tenant_id="t")
    with pytest.raises(ValueError, match="tenant_id"):
        await _TenantOwned.get_item("u1", owner_id="o")
    with pytest.raises(ValueError, match="owner_id"):
        await _TenantOwned.get_item("u1", tenant_id="t")

    with patch(
        "fastapi_mongo_base.models.BaseEntity.get_item",
        new=AsyncMock(return_value=None),
    ):
        assert await _UserEnt.get_item("u1", ignore_user_id=True) is None
        assert await _Owned.get_item("u1", ignore_owner_id=True) is None
        assert (
            await _Workspace.get_item("u1", ignore_workspace_id=True) is None
        )
        assert await _Tenant.get_item("u1", tenant_id="t") is None
        assert (
            await _TenantUser.get_item(
                "u1",
                tenant_id="t",
                ignore_user_id=True,
            )
            is None
        )
        assert (
            await _TenantWs.get_item(
                "u1",
                tenant_id="t",
                ignore_workspace_id=True,
            )
            is None
        )
        assert (
            await _TenantOwned.get_item(
                "u1",
                tenant_id="t",
                ignore_owner_id=True,
            )
            is None
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_create_update_field_sets_and_immutable() -> None:
    """create/update honor field sets; immutable blocks mutate/delete."""
    with (
        patch.object(
            TestEntity,
            "create_field_set",
            return_value=["name", "number"],
        ),
        patch.object(
            TestEntity,
            "create_exclude_set",
            return_value=["meta_data"],
        ),
    ):
        item = await TestEntity.create_item({
            "name": "keep",
            "number": 2,
            "meta_data": {"x": 1},
            "uid": "nope",
        })
    assert item.name == "keep"

    with (
        patch.object(
            TestEntity,
            "update_field_set",
            return_value=["name", "number"],
        ),
        patch.object(
            TestEntity,
            "update_exclude_set",
            return_value=["number"],
        ),
    ):
        updated = await TestEntity.update_item(
            item,
            {"name": "next", "number": 99},
        )
    assert updated.name == "next"
    assert updated.number == 2

    class _ImmSchema(BaseEntitySchema):
        name: str = "imm"

    class _Imm(_ImmSchema, ImmutableMixin):
        class Settings(ImmutableMixin.Settings):
            name = "coverage_immutable_entities"
            __abstract__ = True

    imm = _Imm(name="locked")
    with pytest.raises(ValueError, match="cannot be updated"):
        await _Imm.update_item(imm, {"name": "x"})
    with pytest.raises(ValueError, match="cannot be deleted"):
        await _Imm.delete_item(imm)
