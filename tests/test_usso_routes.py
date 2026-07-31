"""Test usso routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

try:
    import usso  # ruff:ignore[unused-import]

    _USSO_IS_REAL = True
except ImportError:
    from tests.helpers.usso_mock import install_usso_mock

    install_usso_mock()
    _USSO_IS_REAL = False

from usso.user import UserData

from src.fastapi_mongo_base.errors.status import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from src.fastapi_mongo_base.utils.usso_routes import (
    AbstractOwnedUSSORouter,
    AbstractTenantUSSORouter,
)

_requires_real_usso = pytest.mark.skipif(
    not _USSO_IS_REAL,
    reason=(
        "exercises real usso.authorization semantics; the fallback stub's "
        "owner_authorization/broadest_scope_filter are no-ops, not a "
        "faithful reimplementation"
    ),
)


_AUTH = "src.fastapi_mongo_base.utils.usso_routes.authorization"


class _ItemSchema(BaseModel):
    uid: str = "item-1"
    user_id: str | None = None
    owner_id: str | None = None
    tenant_id: str | None = None


class _TenantRouter(AbstractTenantUSSORouter):
    namespace = "ns"
    service = "svc"
    resource = "items"
    model = MagicMock()
    schema = _ItemSchema


class _OwnedRouter(AbstractOwnedUSSORouter):
    namespace = "ns"
    service = "svc"
    resource = "items"
    model = MagicMock()
    schema = _ItemSchema
    workspace_only = False


@pytest.fixture()
def tenant_router() -> _TenantRouter:
    """Fixture for tenant router."""
    router = object.__new__(_TenantRouter)
    router.model = MagicMock()
    router.schema = _ItemSchema
    return router


@pytest.fixture()
def owned_router() -> _OwnedRouter:
    """Fixture for owned router."""
    router = object.__new__(_OwnedRouter)
    router.model = MagicMock()
    router.schema = _ItemSchema
    return router


def test_resource_path_builds_namespace_service_resource(
    tenant_router: _TenantRouter,
) -> None:
    """resource_path joins namespace, service, and resource."""
    assert tenant_router.resource_path == "ns/svc/items"


@pytest.mark.asyncio
async def test_authorize_raises_unauthorized_when_user_missing(
    tenant_router: _TenantRouter,
) -> None:
    """Authorize without user raises UnauthorizedError by default."""
    with pytest.raises(UnauthorizedError):
        await tenant_router.authorize(action="read", user=None)


@pytest.mark.asyncio
async def test_authorize_returns_false_when_user_missing_and_no_raise(
    tenant_router: _TenantRouter,
) -> None:
    """Authorize can return False instead of raising."""
    allowed = await tenant_router.authorize(
        action="read",
        user=None,
        raise_exception=False,
    )
    assert allowed is False


@pytest.mark.asyncio
async def test_authorize_owner_authorization_short_circuit(
    tenant_router: _TenantRouter,
) -> None:
    """owner_authorization success skips scope checks."""
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    with patch(
        f"{_AUTH}.owner_authorization",
        return_value=True,
    ):
        assert await tenant_router.authorize(action="read", user=user) is True


@pytest.mark.asyncio
async def test_authorize_forwards_workspace_id_and_action(
    tenant_router: _TenantRouter,
) -> None:
    """
    Test that authorize() forwards workspace_id/workspace_action.

    This is the wiring that lets a workspace member's request be granted
    for resources they didn't create.
    """
    user = UserData(
        sub="user-1", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    with patch(
        f"{_AUTH}.owner_authorization", return_value=True
    ) as mock_owner_auth:
        await tenant_router.authorize(action="read", user=user)
    assert mock_owner_auth.call_args.kwargs["workspace_id"] == "ws-1"
    assert mock_owner_auth.call_args.kwargs["workspace_action"] == "read"


@pytest.mark.asyncio
async def test_authorize_workspace_access_false_omits_workspace_kwargs(
    tenant_router: _TenantRouter,
) -> None:
    """workspace_access=False disables the workspace_id passthrough."""
    tenant_router.workspace_access = False
    user = UserData(
        sub="user-1", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    with patch(
        f"{_AUTH}.owner_authorization", return_value=True
    ) as mock_owner_auth:
        await tenant_router.authorize(action="read", user=user)
    assert "workspace_id" not in mock_owner_auth.call_args.kwargs


@_requires_real_usso
@pytest.mark.asyncio
async def test_authorize_grants_workspace_member_read_end_to_end(
    tenant_router: _TenantRouter,
) -> None:
    """
    Test end-to-end (real owner_authorization, not mocked).

    A workspace member can read a resource created by someone else in
    the same workspace, up to the router's workspace_action (default
    "read").
    """
    user = UserData(
        sub="user-2", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    resource_filter = {"user_id": "user-1", "workspace_id": "ws-1"}
    assert await tenant_router.authorize(
        action="read", user=user, filter_data=resource_filter
    )


@_requires_real_usso
@pytest.mark.asyncio
async def test_authorize_denies_workspace_member_write_by_default(
    tenant_router: _TenantRouter,
) -> None:
    """
    Test end-to-end (real owner_authorization).

    A workspace member cannot update/delete another member's resource
    under the default read-only workspace_action, and falls through to
    the (failing) scope check.
    """
    user = UserData(
        sub="user-2", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    resource_filter = {"user_id": "user-1", "workspace_id": "ws-1"}
    with pytest.raises(ForbiddenError):
        await tenant_router.authorize(
            action="update", user=user, filter_data=resource_filter
        )


@pytest.mark.asyncio
async def test_authorize_raises_forbidden_when_scopes_deny(
    tenant_router: _TenantRouter,
) -> None:
    """Failed scope check raises ForbiddenError."""
    user = UserData(sub="user-1", tenant_id="t1", scopes=["read:other"])
    with (
        patch(
            f"{_AUTH}.owner_authorization",
            return_value=False,
        ),
        patch(
            f"{_AUTH}.check_access",
            return_value=False,
        ),
        pytest.raises(ForbiddenError),
    ):
        await tenant_router.authorize(action="read", user=user)


@pytest.mark.asyncio
async def test_authorize_returns_false_when_scopes_deny_and_no_raise(
    tenant_router: _TenantRouter,
) -> None:
    """Failed scope check returns False when raise_exception is False."""
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    with (
        patch(
            f"{_AUTH}.owner_authorization",
            return_value=False,
        ),
        patch(
            f"{_AUTH}.check_access",
            return_value=False,
        ),
    ):
        allowed = await tenant_router.authorize(
            action="read",
            user=user,
            raise_exception=False,
        )
        assert allowed is False


def test_get_list_filter_queries_adds_owner_when_self_access(
    tenant_router: _TenantRouter,
) -> None:
    """self_access adds owner filter from resolved owner id."""
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    tenant_router.model = MagicMock()
    tenant_router.model.user_id = "user_id"
    with (
        patch(
            f"{_AUTH}.get_scope_filters",
            return_value=[],
        ),
        patch(
            f"{_AUTH}.broadest_scope_filter",
            side_effect=lambda scopes: scopes[0],
        ),
    ):
        filters = tenant_router.get_list_filter_queries(user=user)
    assert filters == {"user_id": "user-1"}


def test_get_list_filter_queries_denies_without_scopes(
    tenant_router: _TenantRouter,
) -> None:
    """No scopes and no self_access yields deny marker."""
    router = tenant_router
    router.self_access = False
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    with patch(
        f"{_AUTH}.get_scope_filters",
        return_value=[],
    ):
        assert router.get_list_filter_queries(user=user) == {"__deny__": True}


@_requires_real_usso
def test_get_list_filter_queries_prefers_workspace_over_user(
    tenant_router: _TenantRouter,
) -> None:
    """
    Test that a workspace member's list filter becomes workspace-wide.

    Not just their own items -- broadest_scope_filter (real, not mocked
    here) already scores workspace_id as less restrictive than user_id,
    so no extra query-builder support is needed for shared visibility.
    """
    user = UserData(
        sub="user-1", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    with patch(f"{_AUTH}.get_scope_filters", return_value=[]):
        filters = tenant_router.get_list_filter_queries(user=user)
    assert filters == {"workspace_id": "ws-1"}


def test_get_list_filter_queries_workspace_access_false(
    tenant_router: _TenantRouter,
) -> None:
    """workspace_access=False omits the workspace candidate entirely."""
    tenant_router.workspace_access = False
    user = UserData(
        sub="user-1", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    with patch(f"{_AUTH}.get_scope_filters", return_value=[]):
        filters = tenant_router.get_list_filter_queries(user=user)
    assert filters == {"user_id": "user-1"}


def test_get_list_filter_queries_skips_workspace_without_field(
    tenant_router: _TenantRouter,
) -> None:
    """Models without a workspace_id field are unaffected."""
    tenant_router.model = MagicMock(spec=["uid", "user_id", "tenant_id"])
    user = UserData(
        sub="user-1", tenant_id="t1", workspace_id="ws-1", scopes=[]
    )
    with patch(f"{_AUTH}.get_scope_filters", return_value=[]):
        filters = tenant_router.get_list_filter_queries(user=user)
    assert filters == {"user_id": "user-1"}


def test_get_list_filter_queries_no_workspace_id_on_user(
    tenant_router: _TenantRouter,
) -> None:
    """A user with no current workspace_id gets the plain owner filter."""
    user = UserData(sub="user-1", tenant_id="t1", workspace_id=None, scopes=[])
    with patch(f"{_AUTH}.get_scope_filters", return_value=[]):
        filters = tenant_router.get_list_filter_queries(user=user)
    assert filters == {"user_id": "user-1"}


@pytest.mark.asyncio
async def test_get_item_raises_not_found(tenant_router: _TenantRouter) -> None:
    """get_item raises NotFoundError when model returns None."""
    tenant_router.model.get_item = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await tenant_router.get_item(uid="missing", tenant_id="t1")


@pytest.mark.asyncio
async def test_list_items_raises_forbidden_on_deny(
    tenant_router: _TenantRouter,
) -> None:
    """_list_items raises when filters contain __deny__."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    tenant_router.get_user = AsyncMock(return_value=user)
    with (
        patch.object(
            tenant_router,
            "get_list_filter_queries",
            return_value={"__deny__": True},
        ),
        pytest.raises(ForbiddenError),
    ):
        await tenant_router._list_items(request)


@pytest.mark.asyncio
async def test_create_item_persists_owner_and_tenant(
    tenant_router: _TenantRouter,
) -> None:
    """create_item authorizes and sets owner plus tenant_id."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = MagicMock()
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router.authorize = AsyncMock(return_value=True)
    tenant_router.model.create_item = AsyncMock(return_value=item)
    result = await tenant_router.create_item(request, {"title": "x"})
    assert result is item
    tenant_router.model.create_item.assert_awaited_once_with({
        "title": "x",
        "user_id": "user-1",
        "tenant_id": "t1",
    })


def test_tenant_router_owner_id_for_create_uses_user_id(
    tenant_router: _TenantRouter,
) -> None:
    """Tenant router create owner defaults to JWT user_id claim."""
    user = UserData(sub="uid-1", tenant_id="t1", user_id="create-user")
    assert tenant_router._owner_id_for_create(user) == "create-user"


def test_owned_router_get_owner_id_prefers_workspace(
    owned_router: _OwnedRouter,
) -> None:
    """Owned router returns workspace_id when workspace_only is enabled."""
    owned_router.workspace_only = True
    user = UserData(
        sub="user-1",
        tenant_id="t1",
        workspace_id="ws-9",
        scopes=[],
    )
    assert owned_router.get_owner_id(user) == "ws-9"


def test_owned_router_get_owner_id_falls_back_to_user_id(
    owned_router: _OwnedRouter,
) -> None:
    """Non-workspace mode falls back to user_id."""
    user = UserData(sub="user-1", tenant_id="t1", workspace_id=None, scopes=[])
    assert owned_router.get_owner_id(user) == "user-1"


@pytest.mark.asyncio
async def test_list_items_returns_paginated_response(
    tenant_router: _TenantRouter,
) -> None:
    """_list_items returns validated paginated items."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = _ItemSchema(uid="item-1", user_id="user-1")
    tenant_router.list_item_schema = _ItemSchema
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router.model.list_total_combined = AsyncMock(
        return_value=([item], 1)
    )
    with patch.object(
        tenant_router,
        "get_list_filter_queries",
        return_value={},
    ):
        resp = await tenant_router._list_items(request, offset=0, limit=10)
    assert resp.total == 1
    assert len(resp.items) == 1


@pytest.mark.asyncio
async def test_list_items_returns_empty_when_deny_without_raise(
    tenant_router: _TenantRouter,
) -> None:
    """_list_items can return empty page instead of raising."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    tenant_router.get_user = AsyncMock(return_value=user)
    with patch.object(
        tenant_router,
        "get_list_filter_queries",
        return_value={"__deny__": True},
    ):
        resp = await tenant_router._list_items(
            request,
            raise_exception=False,
        )
    assert resp.total == 0
    assert resp.items == []


@pytest.mark.asyncio
async def test_retrieve_item_authorizes_and_returns_item(
    tenant_router: _TenantRouter,
) -> None:
    """retrieve_item loads item and runs read authorization."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = MagicMock()
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router.get_item = AsyncMock(return_value=item)
    tenant_router.authorize = AsyncMock(return_value=True)
    result = await tenant_router.retrieve_item(request, "item-1")
    assert result is item
    tenant_router.authorize.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_item_authorizes_and_persists(
    tenant_router: _TenantRouter,
) -> None:
    """update_item authorizes against existing item then updates."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = MagicMock()
    updated = MagicMock()
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router.get_item = AsyncMock(return_value=item)
    tenant_router.authorize = AsyncMock(return_value=True)
    tenant_router.model.update_item = AsyncMock(return_value=updated)
    result = await tenant_router.update_item(
        request, "item-1", {"title": "new"}
    )
    assert result is updated
    tenant_router.model.update_item.assert_awaited_once_with(
        item, {"title": "new"}
    )


@pytest.mark.asyncio
async def test_delete_item_authorizes_and_deletes(
    tenant_router: _TenantRouter,
) -> None:
    """delete_item authorizes against existing item then deletes."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = MagicMock()
    deleted = MagicMock()
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router.get_item = AsyncMock(return_value=item)
    tenant_router.authorize = AsyncMock(return_value=True)
    tenant_router.model.delete_item = AsyncMock(return_value=deleted)
    result = await tenant_router.delete_item(request, "item-1")
    assert result is deleted


@pytest.mark.asyncio
async def test_mine_items_creates_default_when_empty(
    tenant_router: _TenantRouter,
) -> None:
    """mine_items auto-creates when configured and list is empty."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    created = MagicMock()
    tenant_router.create_mine_if_not_found = True
    tenant_router.unique_per_user = False
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router._list_items = AsyncMock(
        return_value=type(
            "Resp",
            (),
            {"items": [], "total": 0, "offset": 0, "limit": 10},
        )(),
    )
    tenant_router.model.create_item = AsyncMock(return_value=created)
    resp = await tenant_router.mine_items(request)
    assert resp.total == 1
    assert resp.items == [created]


@pytest.mark.asyncio
async def test_mine_items_returns_single_item_when_unique_per_user(
    tenant_router: _TenantRouter,
) -> None:
    """unique_per_user returns the first item instead of paginated response."""
    request = MagicMock()
    user = UserData(sub="user-1", tenant_id="t1", scopes=["*:*"])
    item = _ItemSchema(uid="only-one")
    tenant_router.unique_per_user = True
    tenant_router.get_user = AsyncMock(return_value=user)
    tenant_router._list_items = AsyncMock(
        return_value=type(
            "Resp",
            (),
            {"items": [item], "total": 1, "offset": 0, "limit": 10},
        )(),
    )
    result = await tenant_router.mine_items(request)
    assert result.uid == "only-one"


def test_owner_id_for_create_uses_custom_getter(
    tenant_router: _TenantRouter,
) -> None:
    """Custom get_owner_id_for_create overrides default resolution."""
    user = UserData(sub="user-1", tenant_id="t1", scopes=[])
    tenant_router.get_owner_id_for_create = lambda _user: "custom-owner"
    assert tenant_router._owner_id_for_create(user) == "custom-owner"
