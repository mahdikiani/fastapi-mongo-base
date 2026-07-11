"""Tests for i18n helpers and language catalog."""

import pytest
from fastapi import Request

from src.fastapi_mongo_base.i18n import (
    localized,
    parse_accept_language,
    select_localized_messages,
    select_request_messages,
)
from src.fastapi_mongo_base.i18n.languages import Language


def test_language_metadata_and_code_lookup() -> None:
    """Language catalog exposes stable metadata and locale codes."""
    assert Language.Persian.code == "fa"
    assert Language.Persian.fa == "فارسی"
    assert Language.from_code("fa-IR") is Language.Persian
    assert Language.has_code("fa") is True
    assert Language.has_value("Persian") is True
    assert Language.has_code("zz") is False


def test_language_get_choices_includes_value() -> None:
    """Choices remain compatible with previous API shape."""
    choices = Language.get_choices()
    persian = next(item for item in choices if item["abbreviation"] == "fa")

    assert persian["en"] == "Persian"
    assert persian["value"] == "Persian"


def test_localized_builds_message_dict() -> None:
    """localized() creates locale-keyed dictionaries."""
    assert localized("Hello", "سلام") == {"en": "Hello", "fa": "سلام"}
    assert localized("Hello") == {"en": "Hello"}


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, []),
        ("fa-IR, en;q=0.8", ["fa", "en"]),
        ("en-US,en;q=0.9,fa;q=0.8", ["en", "fa"]),
    ],
)
def test_parse_accept_language(
    header: str | None,
    expected: list[str],
) -> None:
    """Accept-Language parsing preserves order and strips regions."""
    assert parse_accept_language(header) == expected


def test_select_localized_messages_filters_and_falls_back() -> None:
    """Message selection filters by locale and falls back when needed."""
    messages = localized("Hello", "سلام")

    assert select_localized_messages(messages, ["fa"]) == {"fa": "سلام"}
    assert select_localized_messages(messages, ["de"]) == messages
    assert select_localized_messages(messages, []) == messages


def test_select_request_messages_uses_header() -> None:
    """Request helper reads Accept-Language from FastAPI request."""
    request = Request(
        {
            "type": "http",
            "headers": [(b"accept-language", b"fa-IR, en;q=0.5")],
            "method": "GET",
            "path": "/",
        }
    )

    selected = select_request_messages(
        request,
        localized("Validation error", "خطای اعتبارسنجی"),
    )

    assert selected == {
        "fa": "خطای اعتبارسنجی",
        "en": "Validation error",
    }
