"""Tests for delegated create authorization helpers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.fastapi_mongo_base.schemas import (
    OwnedOverrideCreateMixin,
    OwnerOverrideCreateMixin,
)
from src.fastapi_mongo_base.utils.delegated_create import (
    authorize_create_on_behalf,
    dump_create_payload,
    get_owner_value,
    is_service_request,
    resolve_owner_id_for_create,
    set_owner_value,
)


class _CreatePayload(OwnerOverrideCreateMixin):
    title: str = "item"


class _OwnedCreatePayload(OwnedOverrideCreateMixin):
    title: str = "item"


class _Request:
    """Mock request object."""

    def __init__(self, headers: dict[str, str]) -> None:
        """Initialize request object."""
        self.headers = headers


class _Router:
    owner_attr = "user_id"

    def __init__(self) -> None:
        self.authorize = AsyncMock(return_value=True)


@pytest.mark.asyncio
async def test_jwt_self_create_skips_authorize() -> None:
    """JWT users creating for themselves skip extra create authorization."""
    router = _Router()
    request = _Request({})
    data = _CreatePayload()
    user = MagicMock()

    owner_id = await authorize_create_on_behalf(
        router,
        request,
        user,
        data,
        default_owner_id="user-1",
        authenticated_owner_id="user-1",
    )

    assert owner_id == "user-1"
    assert data.user_id == "user-1"
    router.authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_jwt_delegated_create_requires_authorize() -> None:
    """JWT users creating for another owner must authorize."""
    router = _Router()
    request = _Request({})
    data = _CreatePayload(user_id="user-2")
    user = MagicMock()

    owner_id = await authorize_create_on_behalf(
        router,
        request,
        user,
        data,
        default_owner_id="user-1",
        authenticated_owner_id="user-1",
    )

    assert owner_id == "user-2"
    router.authorize.assert_awaited_once_with(
        action="create",
        user=user,
        filter_data=dump_create_payload(data),
    )


@pytest.mark.asyncio
async def test_service_request_skips_authorize_for_delegated_owner() -> None:
    """Service requests may create for another user without authorize."""
    router = _Router()
    request = _Request({"x-api-key": "service-key"})
    data = _CreatePayload(user_id="user-2")
    user = MagicMock()

    owner_id = await authorize_create_on_behalf(
        router,
        request,
        user,
        data,
        default_owner_id="service-1",
        authenticated_owner_id="service-1",
    )

    assert owner_id == "user-2"
    router.authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_require_create_authorization_for_self() -> None:
    """Billing-style routers can force create authorization even for self."""
    router = _Router()
    request = _Request({})
    data = _CreatePayload()
    user = MagicMock()

    await authorize_create_on_behalf(
        router,
        request,
        user,
        data,
        default_owner_id="user-1",
        authenticated_owner_id="user-1",
        require_create_authorization=True,
    )

    router.authorize.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_attr_owner_id() -> None:
    """Delegated create works with owner_id ownership field."""
    router = _Router()
    router.owner_attr = "owner_id"
    request = _Request({})
    data = _OwnedCreatePayload(owner_id="owner-9")
    user = MagicMock()

    owner_id = await authorize_create_on_behalf(
        router,
        request,
        user,
        data,
        owner_attr="owner_id",
        default_owner_id="owner-1",
        authenticated_owner_id="owner-1",
    )

    assert owner_id == "owner-9"


def test_is_service_request_detects_api_key_header() -> None:
    """Service requests are detected from x-api-key header."""
    assert is_service_request(_Request({"x-api-key": "abc"})) is True
    assert is_service_request(_Request({})) is False


def test_is_service_request_requires_headers_mapping() -> None:
    """Invalid request objects raise TypeError."""
    with pytest.raises(TypeError, match="headers mapping"):
        is_service_request(object())


@pytest.mark.asyncio
async def test_authorize_create_on_behalf_requires_router() -> None:
    """Router must implement authorize()."""
    with pytest.raises(TypeError, match="authorize"):
        await authorize_create_on_behalf(
            object(),
            _Request({}),
            MagicMock(),
            _CreatePayload(),
            default_owner_id="u1",
            authenticated_owner_id="u1",
        )


@pytest.mark.asyncio
async def test_authorize_create_on_behalf_requires_user() -> None:
    """User argument is required."""
    router = _Router()
    with pytest.raises(TypeError, match="user is required"):
        await authorize_create_on_behalf(
            router,
            _Request({}),
            None,
            _CreatePayload(),
            default_owner_id="u1",
            authenticated_owner_id="u1",
        )


@pytest.mark.asyncio
async def test_service_user_skips_authorize() -> None:
    """Service sub_type bypasses create authorization."""
    router = _Router()
    user = MagicMock()
    user.claims = {"sub_type": "agent"}
    data = _CreatePayload(user_id="other-user")

    owner_id = await authorize_create_on_behalf(
        router,
        _Request({}),
        user,
        data,
        default_owner_id="caller",
        authenticated_owner_id="caller",
    )

    assert owner_id == "other-user"
    router.authorize.assert_not_awaited()


def test_get_owner_value_rejects_invalid_payload() -> None:
    """Owner helpers reject unsupported payload types."""
    with pytest.raises(TypeError, match="Pydantic model or dict"):
        get_owner_value([], "user_id")


def test_resolve_owner_value_on_dict() -> None:
    """Owner helpers support plain dict payloads."""
    payload: dict[str, str | None] = {"user_id": None}
    assert (
        resolve_owner_id_for_create(
            payload,
            owner_attr="user_id",
            default_owner_id="user-1",
        )
        == "user-1"
    )
    assert payload["user_id"] == "user-1"

    set_owner_value(payload, "user_id", "user-2")
    assert get_owner_value(payload, "user_id") == "user-2"


def test_set_owner_value_rejects_invalid_payload() -> None:
    """set_owner_value rejects unsupported payload types."""
    with pytest.raises(TypeError, match="Pydantic model or dict"):
        set_owner_value([], "user_id", "u1")


def test_dump_create_payload_rejects_invalid_payload() -> None:
    """dump_create_payload rejects unsupported payload types."""
    with pytest.raises(TypeError, match="Pydantic model or dict"):
        dump_create_payload(123)
