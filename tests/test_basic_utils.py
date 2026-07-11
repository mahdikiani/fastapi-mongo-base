"""Tests for basic utility helpers."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.fastapi_mongo_base.utils import basic


class _ChildEntity:
    """Unused helper for subclass traversal tests."""


class _ParentEntity:
    pass


class _DerivedEntity(_ParentEntity):
    pass


def test_get_all_subclasses_returns_nested_subclasses() -> None:
    """get_all_subclasses collects direct and nested subclasses."""
    subclasses = basic.get_all_subclasses(_ParentEntity)
    assert _DerivedEntity in subclasses


def test_parse_array_parameter_from_list() -> None:
    """Lists are deduplicated and returned as list."""
    assert set(basic.parse_array_parameter(["a", "a", "b"])) == {"a", "b"}


def test_parse_array_parameter_from_json_array() -> None:
    """JSON array strings are parsed."""
    assert set(basic.parse_array_parameter('["x", "y", "x"]')) == {"x", "y"}


def test_parse_array_parameter_from_comma_separated() -> None:
    """Comma-separated strings are split."""
    assert set(basic.parse_array_parameter("one, two , three")) == {
        "one",
        "two",
        "three",
    }


def test_parse_array_parameter_single_value() -> None:
    """Non-string scalars become single-item lists."""
    assert basic.parse_array_parameter(42) == [42]


def test_get_base_field_name_strips_suffix() -> None:
    """Query suffixes are removed from field names."""
    assert basic.get_base_field_name("created_at_from") == "created_at"
    assert basic.get_base_field_name("amount.gte") == "amount"


def test_is_valid_range_value() -> None:
    """Range queries accept numeric and temporal types."""
    assert basic.is_valid_range_value(1) is True
    assert basic.is_valid_range_value(Decimal("1.5")) is True
    assert basic.is_valid_range_value(datetime(2024, 1, 1)) is True
    assert basic.is_valid_range_value(date(2024, 1, 1)) is True
    assert basic.is_valid_range_value("x") is True
    assert basic.is_valid_range_value([]) is False


def test_try_except_wrapper_swallows_sync_errors() -> None:
    """Sync wrapper logs and returns None on failure."""

    @basic.try_except_wrapper
    def boom() -> None:
        msg = "fail"
        raise ValueError(msg)

    assert boom() is None


@pytest.mark.asyncio
async def test_try_except_wrapper_async_path() -> None:
    """Async wrapper runs coroutine functions."""

    @basic.try_except_wrapper
    async def ok() -> str:
        await asyncio.sleep(0)
        return "done"

    assert await ok() == "done"


def test_delay_execution_runs_after_sleep() -> None:
    """delay_execution waits before invoking the wrapped function."""
    calls: list[int] = []

    @basic.delay_execution(0)
    def record() -> None:
        calls.append(1)

    record()
    assert calls == [1]


def test_retry_execution_succeeds_on_second_attempt() -> None:
    """retry_execution retries until success."""
    attempts = {"count": 0}

    @basic.retry_execution(attempts=2, delay=0, sync_to_thread=False)
    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            msg = "not yet"
            raise RuntimeError(msg)
        return "ok"

    assert flaky() == "ok"


def test_retry_execution_raises_after_exhausting_attempts() -> None:
    """retry_execution re-raises when all attempts fail."""

    @basic.retry_execution(attempts=2, delay=0, sync_to_thread=False)
    def always_fails() -> None:
        msg = "nope"
        raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="nope"):
        always_fails()


@pytest.mark.asyncio
async def test_gather_sync_parallel_and_sequential() -> None:
    """gather_sync supports parallel and sequential execution."""

    async def one() -> int:
        await asyncio.sleep(0)
        return 1

    async def two() -> int:
        await asyncio.sleep(0)
        return 2

    parallel = await basic.gather_sync([one(), two()], sync=False)
    sequential = await basic.gather_sync([one(), two()], sync=True)
    assert parallel == [1, 2]
    assert sequential == [1, 2]


@pytest.mark.asyncio
async def test_debug_mode_mock_returns_mock_when_debug_enabled() -> None:
    """debug_mode_mock short-circuits when Settings.debug is True."""

    @basic.debug_mode_mock("mocked")
    async def real() -> str:
        await asyncio.sleep(0)
        return "real"

    with patch("src.fastapi_mongo_base.core.config.Settings.debug", True):
        assert await real() == "mocked"


@pytest.mark.asyncio
async def test_debug_mode_mock_calls_real_when_debug_disabled() -> None:
    """debug_mode_mock delegates to the wrapped function when debug is off."""

    @basic.debug_mode_mock("mocked")
    async def real() -> str:
        await asyncio.sleep(0)
        return "real"

    with patch("src.fastapi_mongo_base.core.config.Settings.debug", False):
        assert await real() == "real"


def test_debug_mode_mock_sync_wrapper() -> None:
    """debug_mode_mock supports sync functions."""

    @basic.debug_mode_mock(lambda *_a, **_k: "from-callable")
    def real() -> str:
        return "real"

    with patch("src.fastapi_mongo_base.core.config.Settings.debug", True):
        assert real() == "from-callable"


def test_sync_retry_wrapper() -> None:
    """Sync retry wrapper succeeds without asyncio."""

    @basic.retry_execution(attempts=1, delay=0, sync_to_thread=False)
    def ok() -> int:
        return 7

    assert ok() == 7


def test_sync_try_except_wrapper() -> None:
    """Sync try_except wrapper catches exceptions."""

    @basic.try_except_wrapper
    def boom() -> None:
        msg = "sync fail"
        raise ValueError(msg)

    assert boom() is None
