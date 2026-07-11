"""Tests for USSO service principal detection."""

from dataclasses import dataclass, field

import pytest

from src.fastapi_mongo_base.utils.usso.principals import (
    is_service_auth,
    is_service_request,
    is_service_user,
)


@dataclass
class _Request:
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class _User:
    claims: dict[str, object] | None = None


def test_is_service_request_detects_api_key_header() -> None:
    """API key header marks a service request."""
    assert is_service_request(_Request({"x-api-key": "abc"})) is True
    assert is_service_request(_Request({"X-Api-Key": "abc"})) is True
    assert is_service_request(_Request({})) is False


@pytest.mark.parametrize(
    ("sub_type", "expected"),
    [
        ("agent", True),
        ("api_key", True),
        ("user", False),
        (None, False),
    ],
)
def test_is_service_user_from_sub_type(
    sub_type: str | None,
    expected: bool,
) -> None:
    """Service principals are identified by USSO sub_type claim."""
    claims = {"sub_type": sub_type} if sub_type is not None else {}
    assert is_service_user(_User(claims)) is expected


def test_is_service_auth_combines_request_and_user() -> None:
    """Either API key header or service sub_type counts as service auth."""
    user = _User({"sub_type": "agent"})
    request = _Request({})
    assert is_service_auth(request=_Request({"x-api-key": "k"})) is True
    assert is_service_auth(user=user, request=request) is True
    assert is_service_auth(user=_User({"sub_type": "user"})) is False
