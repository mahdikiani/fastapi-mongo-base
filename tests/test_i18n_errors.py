"""Tests for bilingual error message helpers."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from fastapi_mongo_base.core.app_factory import setup_exception_handlers
from fastapi_mongo_base.core.errors.resource_errors import (
    ResourceNotFoundError,
)
from fastapi_mongo_base.core.exceptions import (
    BaseHTTPException,
    error_messages,
    map_exception_message,
)


def test_map_exception_message_includes_fa_only_when_provided() -> None:
    """Make message map omits fa when it is not provided."""
    assert map_exception_message("Hello") == {"en": "Hello"}
    assert map_exception_message("Hello", "سلام") == {
        "en": "Hello",
        "fa": "سلام",
    }
    assert map_exception_message("Hello", None) == {"en": "Hello"}


def test_subclass_messages_inherit_parent_defaults() -> None:
    """Subclass default_message inherits parent fa automatically."""

    class CustomNotFoundError(ResourceNotFoundError):
        default_message = "Order not found"

    exc = CustomNotFoundError()
    assert exc.message == {
        "en": "Order not found",
        "fa": ResourceNotFoundError.default_message_fa,
    }


def test_subclass_with_en_only_message_uses_parent_fa() -> None:
    """Passing only en in message still uses parent fa translation."""

    class CustomNotFoundError(ResourceNotFoundError):
        default_message = "Order not found"

    exc = CustomNotFoundError(message={"en": "Order missing"})
    assert exc.message == {
        "en": "Order missing",
        "fa": ResourceNotFoundError.default_message_fa,
    }


def test_custom_subclass_keeps_parent_fa() -> None:
    """Custom subclass responses keep the parent Persian message."""

    class CustomNotFoundError(ResourceNotFoundError):
        default_message = "Order not found"

    exc = CustomNotFoundError()
    assert exc.message["fa"] == ResourceNotFoundError.default_message_fa


def test_generate_response_error_localizes_detail() -> None:
    """Generate response error localizes detail from Accept-Language."""
    fa_request = SimpleNamespace(headers={"accept-language": "fa"})
    content = BaseHTTPException.generate_response_error(
        fa_request,  # type: ignore[arg-type]
        message={"en": "Not found", "fa": "یافت نشد"},
        error="item_not_found",
        detail=None,
        data={"uid": "1"},
    )
    assert content["message"] == {"en": "Not found", "fa": "یافت نشد"}
    assert content["detail"] == "یافت نشد"
    assert content["uid"] == "1"


def test_generate_response_error_defaults_to_en_without_header() -> None:
    """Generate response error defaults to English without Accept-Language."""
    content = BaseHTTPException.generate_response_error(
        None,
        message={"en": "Not found", "fa": "یافت نشد"},
        error="item_not_found",
        detail=None,
    )
    assert content["detail"] == "Not found"


def test_base_http_exception_legacy_error_messages_string() -> None:
    """Base http exception legacy error messages string."""
    error_messages["legacy_code"] = "Legacy English"
    exc = BaseHTTPException(status_code=400, error="legacy_code")
    assert exc.message == {"en": "Legacy English"}
    assert exc.detail == "Legacy English"
    error_messages.pop("legacy_code")


def test_base_http_exception_bilingual_catalog_entry() -> None:
    """Base http exception bilingual catalog entry."""
    error_messages["bilingual_code"] = {
        "en": "English",
        "fa": "فارسی",
    }
    exc = BaseHTTPException(status_code=400, error="bilingual_code")
    assert exc.message["en"] == "English"
    assert exc.message["fa"] == "فارسی"
    error_messages.pop("bilingual_code")


@pytest.fixture
def locale_app() -> FastAPI:
    """FastAPI app with resource error handlers registered."""
    app = FastAPI()
    setup_exception_handlers(app=app)

    @app.get("/not-found")
    async def not_found() -> None:
        raise ResourceNotFoundError(resource="User", uid="abc123")

    return app


@pytest.mark.asyncio
async def test_accept_language_fa_localizes_detail(
    locale_app: FastAPI,
) -> None:
    """Accept language fa localizes detail."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=locale_app,
            raise_app_exceptions=False,
        ),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/not-found",
            headers={"Accept-Language": "fa-IR,fa;q=0.9"},
        )

    body = response.json()
    assert response.status_code == 404
    assert body["message"]["en"] == "User with id 'abc123' not found"
    assert body["message"]["fa"] == "User با شناسه «abc123» پیدا نشد."
    assert body["detail"] == body["message"]["fa"]


@pytest.mark.asyncio
async def test_without_accept_language_defaults_to_en_detail(
    locale_app: FastAPI,
) -> None:
    """Without accept language defaults to en detail."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(
            app=locale_app,
            raise_app_exceptions=False,
        ),
        base_url="http://test",
    ) as client:
        response = await client.get("/not-found")

    body = response.json()
    assert body["detail"] == body["message"]["en"]
