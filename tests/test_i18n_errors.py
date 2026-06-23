"""Tests for bilingual error message helpers."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from fastapi_mongo_base.core.app_factory import setup_exception_handlers
from fastapi_mongo_base.core.errors.i18n import (
    build_messages,
    http_error_content,
    localized_text,
    normalize_messages,
    resolve_locale,
)
from fastapi_mongo_base.core.errors.resource_errors import (
    ResourceNotFoundError,
)
from fastapi_mongo_base.core.exceptions import (
    BaseHTTPException,
    error_messages,
)


def test_build_messages_always_includes_en_and_fa() -> None:
    """Build messages always includes en and fa."""
    assert build_messages("Hello") == {"en": "Hello", "fa": "Hello"}
    assert build_messages("Hello", "سلام") == {"en": "Hello", "fa": "سلام"}


def test_normalize_messages_backward_compatible_string() -> None:
    """Normalize messages backward compatible string."""
    assert normalize_messages("Legacy text", fallback="fb") == {
        "en": "Legacy text",
        "fa": "Legacy text",
    }


def test_normalize_messages_dict_passthrough() -> None:
    """Normalize messages dict passthrough."""
    messages = {"en": "Hi", "fa": "سلام"}
    assert normalize_messages(messages, fallback="fb") == messages


def test_resolve_locale_from_accept_language() -> None:
    """Resolve locale from accept language."""
    fa_request = SimpleNamespace(
        headers={"accept-language": "fa-IR,fa;q=0.9,en;q=0.8"},
    )
    assert resolve_locale(fa_request) == "fa"  # type: ignore[arg-type]

    en_request = SimpleNamespace(headers={"accept-language": "en-US,en;q=0.9"})
    assert resolve_locale(en_request) == "en"  # type: ignore[arg-type]


def test_localized_text_falls_back_to_en() -> None:
    """Localized text falls back to en."""
    assert localized_text({"en": "Hello"}, "fa") == "Hello"


def test_http_error_content_localizes_detail() -> None:
    """Http error content localizes detail."""
    fa_request = SimpleNamespace(headers={"accept-language": "fa"})
    content = http_error_content(
        fa_request,  # type: ignore[arg-type]
        message={"en": "Not found", "fa": "یافت نشد"},
        error="item_not_found",
        detail=None,
        data={"uid": "1"},
    )
    assert content["message"] == {"en": "Not found", "fa": "یافت نشد"}
    assert content["detail"] == "یافت نشد"
    assert content["uid"] == "1"


def test_base_http_exception_legacy_error_messages_string() -> None:
    """Base http exception legacy error messages string."""
    error_messages["legacy_code"] = "Legacy English"
    exc = BaseHTTPException(status_code=400, error="legacy_code")
    assert exc.message == {"en": "Legacy English", "fa": "Legacy English"}
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
