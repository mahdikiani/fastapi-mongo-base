"""Tests for run_apscheduler (graceful apscheduler shutdown)."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from fastapi_mongo_base.core.lifecycle import lifecycle
from fastapi_mongo_base.utils.scheduler import RunningJobs, run_apscheduler

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest


async def _wait_until(
    condition: Callable[[], object], timeout: float = 5
) -> None:
    """
    Poll until a zero-argument callable returns True.

    Args:
        condition: Callable to poll.
        timeout: Maximum seconds to wait.

    Raises:
        TimeoutError: If the condition never holds.

    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError


async def test_running_job_completes_before_scheduler_stops() -> None:
    """A job running at stop time finishes; it is not cancelled."""
    events: list[str] = []

    async def job() -> None:
        events.append("start")
        await asyncio.sleep(0.2)
        events.append("done")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(job, "interval", seconds=0.05, max_instances=1)
    stop = asyncio.Event()
    runner = asyncio.create_task(run_apscheduler(scheduler, stop, timeout=5))

    await _wait_until(lambda: "start" in events)
    stop.set()
    await runner

    assert events[-1] == "done"
    assert events.count("start") == events.count("done")
    assert scheduler.running is False


async def test_job_cancelled_after_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A job longer than the timeout is cancelled with a warning."""
    started = asyncio.Event()

    async def job() -> None:
        started.set()
        await asyncio.sleep(60)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(job, "interval", seconds=0.05, max_instances=1)
    stop = asyncio.Event()
    runner = asyncio.create_task(
        run_apscheduler(scheduler, stop, timeout=0.05)
    )
    await asyncio.wait_for(started.wait(), 5)
    begin = time.monotonic()
    stop.set()
    await runner
    assert time.monotonic() - begin < 2
    assert "Cancelling 1 scheduler job(s)" in caplog.text
    assert scheduler.running is False


async def test_defaults_to_process_stop_event() -> None:
    """Without a stop event, the process lifecycle event ends the run."""
    scheduler = AsyncIOScheduler()
    runner = asyncio.create_task(run_apscheduler(scheduler))
    await _wait_until(lambda: scheduler.running)
    lifecycle.begin_shutdown()
    await asyncio.wait_for(runner, 5)
    assert scheduler.running is False


async def test_already_running_scheduler_is_not_restarted() -> None:
    """A scheduler started by the caller is adopted, then shut down."""
    scheduler = AsyncIOScheduler()
    scheduler.start()
    stop = asyncio.Event()
    stop.set()
    await run_apscheduler(scheduler, stop, timeout=1)
    assert scheduler.running is False


async def test_running_jobs_counter() -> None:
    """The counter handles coalesced runs and never goes negative."""
    running = RunningJobs()
    assert await running.wait_idle(0) is True

    running.on_submitted(SimpleNamespace(scheduled_run_times=[1, 2]))
    running.on_submitted(SimpleNamespace())
    assert running.count == 3
    assert await running.wait_idle(0.01) is False

    for _ in range(4):
        running.on_finished(SimpleNamespace())
    assert running.count == 0
    assert await running.wait_idle(0) is True
