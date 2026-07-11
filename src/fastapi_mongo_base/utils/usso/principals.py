"""Detect USSO service principals (API key, agent) on requests and claims."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

SERVICE_SUB_TYPES = frozenset({"agent", "api_key"})


@runtime_checkable
class RequestWithHeaders(Protocol):
    """Minimal request interface needed to identify API-key requests."""

    headers: Mapping[str, str]


@runtime_checkable
class UserWithClaims(Protocol):
    """Minimal user interface for USSO-style service subject types."""

    claims: Mapping[str, object] | None


def _header_api_key(headers: Mapping[str, str]) -> str | None:
    for name in ("x-api-key", "X-Api-Key", "X-API-Key", "X_API_KEY"):
        value = headers.get(name)
        if value:
            return str(value)
    return None


def is_service_request(request: object) -> bool:
    """Return True when the request authenticated via an API key header."""
    if not isinstance(request, RequestWithHeaders):
        msg = "request must expose headers mapping"
        raise TypeError(msg)
    return _header_api_key(request.headers) is not None


def is_service_user(user: object) -> bool:
    """
    Return True when ``user`` is a service principal (agent or API key).

    Relies on USSO ``sub_type`` claim values ``agent`` and ``api_key``.
    """
    claims = getattr(user, "claims", None)
    if not claims:
        return False
    sub_type = claims.get("sub_type")
    return sub_type in SERVICE_SUB_TYPES


def is_service_auth(
    *,
    request: object | None = None,
    user: object | None = None,
) -> bool:
    """Return True when either the request or user indicates service auth."""
    if request is not None and is_service_request(request):
        return True
    return bool(user is not None and is_service_user(user))
