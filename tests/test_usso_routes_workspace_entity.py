"""Tests for AbstractWorkspaceUSSORouter."""

import pytest
from pydantic import BaseModel

try:
    import usso  # ruff:ignore[unused-import]
except ImportError:
    from tests.helpers.usso_mock import install_usso_mock

    install_usso_mock()

from usso.user import UserData

from src.fastapi_mongo_base.errors.base import BaseHTTPException
from src.fastapi_mongo_base.utils.usso_routes import (
    AbstractWorkspaceUSSORouter,
)


class _DummySchema(BaseModel):
    uid: str = "item-1"


class _WorkspaceEntityRouter(AbstractWorkspaceUSSORouter):
    namespace = "finance"
    service = "accounting"
    resource = "wallet"
    model = _DummySchema
    schema = _DummySchema


@pytest.fixture()
def router() -> _WorkspaceEntityRouter:
    """Fixture for workspace entity router."""
    return object.__new__(_WorkspaceEntityRouter)


def test_workspace_router_uses_workspace_id(
    router: _WorkspaceEntityRouter,
) -> None:
    """Workspace router resolves JWT workspace_id."""
    user = UserData(
        sub="user-1",
        tenant_id="tenant-1",
        workspace_id="ws-1",
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
    )
    assert router._resolve_owner_id(user) == "ws-1"
    assert router.owner_attr == "workspace_id"


def test_workspace_router_raises_without_workspace(
    router: _WorkspaceEntityRouter,
) -> None:
    """Scoped users without workspace get workspace_required."""
    user = UserData(
        sub="user-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
    )
    with pytest.raises(BaseHTTPException) as exc_info:
        router._resolve_owner_id(user)
    assert exc_info.value.error_code == "workspace_required"
