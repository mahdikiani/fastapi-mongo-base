"""Tests for async Conditions registry."""

import asyncio

import pytest

from src.fastapi_mongo_base.utils.conditions import Conditions


@pytest.fixture(autouse=True)
def _reset_conditions() -> None:
    """Isolate tests from the singleton conditions cache."""
    Conditions._conditions.clear()
    yield
    Conditions._conditions.clear()


def test_get_condition_creates_and_reuses() -> None:
    """get_condition returns the same asyncio.Condition per uid."""
    registry = Conditions()
    first = registry.get_condition("uid-1")
    second = registry.get_condition("uid-1")
    assert first is second


def test_cleanup_condition_removes_entry() -> None:
    """cleanup_condition drops a uid from the registry."""
    registry = Conditions()
    registry.get_condition("uid-1")
    registry.cleanup_condition("uid-1")
    assert "uid-1" not in registry._conditions


@pytest.mark.asyncio
async def test_wait_and_release_condition() -> None:
    """release_condition wakes waiters and cleans up."""
    registry = Conditions()

    async def waiter() -> None:
        await registry.wait_condition("job-1")

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    await registry.release_condition("job-1")
    await task
    assert "job-1" not in registry._conditions


@pytest.mark.asyncio
async def test_release_condition_noop_for_unknown_uid() -> None:
    """release_condition is safe when uid was never registered."""
    registry = Conditions()
    await registry.release_condition("missing")
