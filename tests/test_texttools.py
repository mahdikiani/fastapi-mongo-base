"""Tests for text utility helpers."""

from __future__ import annotations

import uuid

from src.fastapi_mongo_base.utils import texttools


def test_json_extractor_parses_embedded_object() -> None:
    """json_extractor pulls JSON from surrounding text."""
    payload = texttools.json_extractor('prefix {"a": 1, "b": "x"} suffix')
    assert payload == {"a": 1, "b": "x"}


def test_format_string_keys() -> None:
    """format_string_keys returns placeholder names."""
    assert texttools.format_string_keys("Hello {name}, id={id}") == {
        "name",
        "id",
    }


def test_format_string_fixer_zips_parallel_lists() -> None:
    """format_string_fixer builds dict rows from parallel lists."""
    rows = texttools.format_string_fixer(a=[1, 2], b=["x", "y"])
    assert rows == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]


def test_escape_markdown() -> None:
    """escape_markdown escapes special characters."""
    assert texttools.escape_markdown("*bold*") == r"\*bold\*"


def test_split_text_respects_chunk_size() -> None:
    """split_text breaks long text into chunks."""
    text = "\n".join("paragraph " * 20 for _ in range(20))
    chunks = texttools.split_text(text, max_chunk_size=50)
    assert len(chunks) > 1
    assert all(len(chunk) <= 50 for chunk in chunks)


def test_convert_to_english_digits() -> None:
    """convert_to_english_digits normalizes unicode digits."""
    assert texttools.convert_to_english_digits("۱۲۳") == "123"


def test_is_valid_uuid() -> None:
    """is_valid_uuid validates UUID strings."""
    value = str(uuid.uuid4())
    assert texttools.is_valid_uuid(value) is True
    assert texttools.is_valid_uuid("not-a-uuid") is False


def test_is_valid_url() -> None:
    """is_valid_url accepts http(s) URLs with host."""
    assert texttools.is_valid_url("https://example.com/path") is True
    assert texttools.is_valid_url("not a url") is False


def test_is_username_and_email_and_phone() -> None:
    """Validation helpers match expected patterns."""
    assert texttools.is_username("user_1") is True
    assert texttools.is_username("1bad") is False
    assert texttools.is_email("user@example.com") is True
    assert texttools.is_phone("555-123-4567") is True


def test_generate_random_chars_length() -> None:
    """generate_random_chars returns requested length."""
    assert len(texttools.generate_random_chars(8)) == 8


def test_remove_whitespace() -> None:
    """remove_whitespace collapses spaces but keeps newlines."""
    assert texttools.remove_whitespace("a   b\nc   d") == "a b\nc d"


def test_sanitize_filename_from_path_and_url() -> None:
    """sanitize_filename strips invalid characters."""
    assert texttools.sanitize_filename("my file!.txt") == "my_file"
    assert texttools.sanitize_filename(
        "https://example.com/docs/report v1.pdf",
        space_remover=True,
    ).endswith("report_v1")
