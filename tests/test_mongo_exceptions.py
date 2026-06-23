"""Tests for automatic MongoDB error handling."""

from collections.abc import AsyncIterator

import httpx
import pytest
from bson.errors import InvalidId
from fastapi import FastAPI
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from fastapi_mongo_base.core.app_factory import setup_exception_handlers


@pytest.fixture
def mongo_error_app() -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app=app)

    @app.get("/duplicate-key")
    async def duplicate_key() -> None:
        raise DuplicateKeyError(
            "E11000 duplicate key error",
            11000,
            {
                "keyPattern": {"email": 1},
                "keyValue": {"email": "a@b.c"},
            },
        )

    @app.get("/wrapped")
    async def wrapped() -> None:
        try:
            raise DuplicateKeyError("E11000 duplicate key error", 11000, {})
        except DuplicateKeyError as err:
            raise RuntimeError("insert failed") from err

    @app.get("/timeout")
    async def timeout() -> None:
        raise ServerSelectionTimeoutError("connection timed out")

    @app.get("/invalid-id")
    async def invalid_id() -> None:
        raise InvalidId("not-a-valid-objectid")

    @app.get("/other")
    async def other() -> None:
        raise ValueError("unrelated")

    return app


@pytest.fixture
async def mongo_error_client(
    mongo_error_app: FastAPI,
) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=mongo_error_app,
            raise_app_exceptions=False,
        ),
        base_url="http://test",
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_duplicate_key_auto_mapped(
    mongo_error_client: httpx.AsyncClient,
) -> None:
    response = await mongo_error_client.get("/duplicate-key")

    assert response.status_code == 409
    body = response.json()
    assert body["error"] == "duplicate_key"
    assert body["field"] == "email"
    assert body["value"] == "a@b.c"
    assert "fa" in body["message"]


@pytest.mark.asyncio
async def test_wrapped_duplicate_key_auto_mapped(
    mongo_error_client: httpx.AsyncClient,
) -> None:
    response = await mongo_error_client.get("/wrapped")

    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_key"


@pytest.mark.asyncio
async def test_connection_timeout_auto_mapped(
    mongo_error_client: httpx.AsyncClient,
) -> None:
    response = await mongo_error_client.get("/timeout")

    assert response.status_code == 503
    assert response.json()["error"] == "mongodb_connection_timeout"


@pytest.mark.asyncio
async def test_invalid_object_id_auto_mapped(
    mongo_error_client: httpx.AsyncClient,
) -> None:
    response = await mongo_error_client.get("/invalid-id")

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_object_id"


@pytest.mark.asyncio
async def test_unrelated_exception_stays_generic(
    mongo_error_client: httpx.AsyncClient,
) -> None:
    response = await mongo_error_client.get("/other")

    assert response.status_code == 500
    assert response.json()["error"] == "Exception"
