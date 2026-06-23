"""Tests for ResourceError exception handling via FastAPI handlers."""

from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from fastapi import FastAPI

from fastapi_mongo_base.core.app_factory import setup_exception_handlers
from fastapi_mongo_base.core.errors.resource_errors import (
    ResourceAlreadyExistsError,
    ResourceConflictError,
    ResourceError,
    ResourceForbiddenError,
    ResourceGoneError,
    ResourceInvalidError,
    ResourceLockedError,
    ResourceNotFoundError,
    ResourceUnauthorizedError,
)

ResourceCase = tuple[
    str,
    Callable[[], Exception],
    int,
    str,
    dict[str, object],
]


RESOURCE_ERROR_CASES: list[ResourceCase] = [
    (
        "base",
        lambda: ResourceError(detail="generic resource failure"),
        400,
        "resource_error",
        {},
    ),
    (
        "not-found",
        lambda: ResourceNotFoundError(resource="User", uid="abc123"),
        404,
        "item_not_found",
        {"resource": "User", "uid": "abc123"},
    ),
    (
        "already-exists",
        lambda: ResourceAlreadyExistsError(
            resource="User", field="email"
        ),
        409,
        "resource_already_exists",
        {"resource": "User", "uid": None, "field": "email"},
    ),
    (
        "unauthorized",
        lambda: ResourceUnauthorizedError(),
        401,
        "unauthorized",
        {},
    ),
    (
        "forbidden",
        lambda: ResourceForbiddenError(resource="User", action="delete"),
        403,
        "forbidden",
        {"resource": "User", "action": "delete"},
    ),
    (
        "conflict",
        lambda: ResourceConflictError(
            resource="Order", reason="already shipped"
        ),
        409,
        "resource_conflict",
        {"resource": "Order", "reason": "already shipped"},
    ),
    (
        "gone",
        lambda: ResourceGoneError(resource="Post", uid="post-1"),
        410,
        "resource_gone",
        {"resource": "Post", "uid": "post-1"},
    ),
    (
        "invalid",
        lambda: ResourceInvalidError(
            resource="User",
            field="age",
            reason="must be positive",
        ),
        422,
        "resource_invalid",
        {
            "resource": "User",
            "field": "age",
            "reason": "must be positive",
        },
    ),
    (
        "locked",
        lambda: ResourceLockedError(resource="Document", uid="doc-9"),
        423,
        "resource_locked",
        {"resource": "Document", "uid": "doc-9"},
    ),
]


@pytest.fixture
def resource_error_app() -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app=app)

    for path, factory, *_ in RESOURCE_ERROR_CASES:

        def make_endpoint(
            exc_factory: Callable[[], Exception] = factory,
        ) -> Callable[[], None]:
            async def endpoint() -> None:
                raise exc_factory()

            return endpoint

        app.add_api_route(
            f"/resource/{path}",
            make_endpoint(),
            methods=["GET"],
        )

    return app


@pytest.fixture
async def resource_error_client(
    resource_error_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=resource_error_app,
            raise_app_exceptions=False,
        ),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "factory", "status_code", "error_code", "extra_fields"),
    RESOURCE_ERROR_CASES,
    ids=[case[0] for case in RESOURCE_ERROR_CASES],
)
async def test_resource_error_handler_returns_structured_json(
    resource_error_client: httpx.AsyncClient,
    path: str,
    factory: Callable[[], Exception],
    status_code: int,
    error_code: str,
    extra_fields: dict[str, object],
) -> None:
    _ = factory
    response = await resource_error_client.get(f"/resource/{path}")

    assert response.status_code == status_code
    body = response.json()
    assert body["error"] == error_code
    assert "message" in body
    assert "en" in body["message"]
    assert "fa" in body["message"]
    assert "detail" in body
    for key, value in extra_fields.items():
        assert body[key] == value


@pytest.mark.asyncio
async def test_resource_not_found_message(
    resource_error_client: httpx.AsyncClient,
) -> None:
    response = await resource_error_client.get("/resource/not-found")

    body = response.json()
    assert body["message"]["en"] == "User with id 'abc123' not found"
    assert "fa" in body["message"]


@pytest.mark.asyncio
async def test_resource_forbidden_message(
    resource_error_client: httpx.AsyncClient,
) -> None:
    response = await resource_error_client.get("/resource/forbidden")

    body = response.json()
    assert body["message"]["en"] == (
        "You are not authorized to delete this User"
    )
    assert body["message"]["fa"] == "شما اجازه delete این User را ندارید."
