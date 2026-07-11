"""Tests for workspace_only owner resolution in AbstractOwnedUSSORouter."""

import pytest
from pydantic import BaseModel

try:
    import usso  # noqa: F401
except ImportError:
    from tests.helpers.usso_mock import install_usso_mock

    install_usso_mock()

from usso.user import UserData

from src.fastapi_mongo_base.errors.base import BaseHTTPException
from src.fastapi_mongo_base.utils.usso_routes import AbstractOwnedUSSORouter


class _DummySchema(BaseModel):
    uid: str = "item-1"


class _WorkspaceRouter(AbstractOwnedUSSORouter):
    namespace = "finance"
    service = "accounting"
    resource = "wallet"
    model = _DummySchema
    schema = _DummySchema
    workspace_only = True


@pytest.fixture()
def router() -> _WorkspaceRouter:
    """Fixture for the workspace router."""
    instance = object.__new__(_WorkspaceRouter)
    return instance


def test_resolve_owner_id_uses_workspace_id(router: _WorkspaceRouter) -> None:
    """
    Test the resolve_owner_id method uses the workspace ID for a scoped user.

    Args:
        router: The workspace router.

    Returns:
        The owner ID.
    """
    user = UserData(
        sub="user-1",
        tenant_id="tenant-1",
        workspace_id="ws-1",
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
    )
    assert router._resolve_owner_id(user) == "ws-1"


def test_resolve_owner_id_raises_without_workspace_for_scoped_user(
    router: _WorkspaceRouter,
) -> None:
    """
    Test resolve_owner_id raises when workspace is missing for scoped user.

    Args:
        router: The workspace router.

    Returns:
        The owner ID.
    """
    user = UserData(
        sub="user-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
    )
    with pytest.raises(BaseHTTPException) as exc_info:
        router._resolve_owner_id(user)
    assert exc_info.value.error_code == "workspace_required"


def test_resolve_owner_id_allows_agent_without_workspace(
    router: _WorkspaceRouter,
) -> None:
    """Agent service principals skip workspace-only enforcement."""
    user = UserData(
        sub="agent-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
        sub_type="agent",
    )
    assert router._resolve_owner_id(user) is None


def test_resolve_owner_id_allows_api_key_without_workspace(
    router: _WorkspaceRouter,
) -> None:
    """API key service principals skip workspace-only enforcement."""
    user = UserData(
        sub="service-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["read:finance/accounting/wallet?workspace_id=ws-1"],
        sub_type="api_key",
    )
    assert router._resolve_owner_id(user) is None


def test_resolve_owner_id_allows_admin_without_workspace(
    router: _WorkspaceRouter,
) -> None:
    """Test that resolve_owner_id allows an admin user without a workspace."""
    user = UserData(
        sub="admin-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["*:*"],
    )
    assert router._resolve_owner_id(user) is None


def test_resolve_owner_id_allows_unfiltered_manage_scope(
    router: _WorkspaceRouter,
) -> None:
    """Test that resolve_owner_id allows an unfiltered manage scope."""
    user = UserData(
        sub="admin-1",
        tenant_id="tenant-1",
        workspace_id=None,
        scopes=["manage:finance/accounting/wallet"],
    )
    assert router._resolve_owner_id(user) is None
