"""Shared helpers for delegated resource creation (create on behalf)."""

from collections.abc import Awaitable, Mapping
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from .usso.principals import is_service_request, is_service_user

__all__ = [
    "authorize_create_on_behalf",
    "dump_create_payload",
    "get_owner_value",
    "is_service_request",
    "is_service_user",
    "resolve_owner_id_for_create",
    "set_owner_value",
]


@runtime_checkable
class AuthenticatedUser(Protocol):
    """Minimal authenticated-user interface needed for task ownership."""

    user_id: str


@runtime_checkable
class UserOwnedCreateData(Protocol):
    """Minimal task payload interface used for delegated creation."""

    user_id: str | None

    def model_dump(self) -> Mapping[str, object]:
        """Serialize the task payload for authorization."""


@runtime_checkable
class AuthorizingRouter(Protocol):
    """Minimal router authorization interface used for delegated creation."""

    def authorize(self, **kwargs: object) -> Awaitable[object]:
        """Authorize an action using the supplied request context."""


def get_owner_value(data: object, owner_attr: str) -> str | None:
    """Read the owner field from a create payload."""
    if isinstance(data, BaseModel):
        value = getattr(data, owner_attr, None)
    elif isinstance(data, dict):
        value = data.get(owner_attr)
    else:
        msg = "data must be a Pydantic model or dict"
        raise TypeError(msg)
    if value is None:
        return None
    return str(value)


def set_owner_value(data: object, owner_attr: str, owner_id: str) -> None:
    """Assign the owner field on a create payload."""
    if isinstance(data, BaseModel):
        setattr(data, owner_attr, owner_id)
    elif isinstance(data, dict):
        data[owner_attr] = owner_id
    else:
        msg = "data must be a Pydantic model or dict"
        raise TypeError(msg)


def dump_create_payload(data: object) -> dict[str, object]:
    """Serialize a create payload for authorization filters."""
    if isinstance(data, BaseModel):
        return data.model_dump()
    if isinstance(data, dict):
        return dict(data)
    msg = "data must be a Pydantic model or dict"
    raise TypeError(msg)


def resolve_owner_id_for_create(
    data: object,
    *,
    owner_attr: str,
    default_owner_id: str,
) -> str:
    """
    Resolve and persist the target owner on a create payload.

    When the payload omits the owner field, ``default_owner_id`` is applied.
    """
    owner_id = get_owner_value(data, owner_attr) or default_owner_id
    set_owner_value(data, owner_attr, owner_id)
    return owner_id


async def authorize_create_on_behalf(
    router: object,
    request: object,
    user: object,
    data: object,
    *,
    owner_attr: str = "user_id",
    default_owner_id: str,
    authenticated_owner_id: str,
    require_create_authorization: bool = False,
) -> str:
    """
    Allow service/API-key callers to create resources for an end user.

    JWT-authenticated users still need normal owner/scope authorization when
    they submit a create for a different owner id.

    When ``require_create_authorization`` is True, JWT users must pass create
    authorization even for their own owner id (e.g. billing or usage metering).
    Service requests (API key header or agent/api_key ``sub_type``) skip the
    extra authorize step.
    """
    if not isinstance(router, AuthorizingRouter):
        msg = "router must implement authorize()"
        raise TypeError(msg)
    if user is None:
        msg = "user is required"
        raise TypeError(msg)

    owner_id = resolve_owner_id_for_create(
        data,
        owner_attr=owner_attr,
        default_owner_id=default_owner_id,
    )

    if is_service_request(request) or is_service_user(user):
        return owner_id

    if not require_create_authorization and owner_id == authenticated_owner_id:
        return owner_id

    await router.authorize(
        action="create",
        user=user,
        filter_data=dump_create_payload(data),
    )
    return owner_id
