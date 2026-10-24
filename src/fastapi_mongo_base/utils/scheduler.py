"""
Run an apscheduler ``AsyncIOScheduler`` with graceful shutdown.

apscheduler 3.x cancels running coroutine jobs in ``shutdown()`` (its asyncio
executor ignores ``wait=True``). :func:`run_apscheduler` pauses the scheduler
on the stop event, waits for running jobs, and only then shuts it down.

Requires the ``scheduler`` extra (``apscheduler>=3.10,<4``).
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi_mongo_base.core import lifecycle
from fastapi_mongo_base.core.config import project_settings

if TYPE_CHECKING:
    from apscheduler.schedulers.base import BaseScheduler

logger = logging.getLogger(__name__)


class RunningJobs:
    """Count running scheduler jobs from apscheduler events."""

    def __init__(self) -> None:
        """Start with no running jobs."""
        self.count = 0
        self._idle = asyncio.Event()
        self._idle.set()

    def on_submitted(self, event: object) -> None:
        """
        Track a submitted job (one per scheduled run time).

        Args:
            event: apscheduler ``JobSubmissionEvent``.

        """
        self.count += len(getattr(event, "scheduled_run_times", ()) or (1,))
        self._idle.clear()

    def on_finished(self, _event: object) -> None:
        """
        Track a finished job run (executed or failed).

        Args:
            _event: apscheduler ``JobExecutionEvent``.

        """
        self.count = max(0, self.count - 1)
        if self.count == 0:
            self._idle.set()

    async def wait_idle(self, timeout: float) -> bool:
        """
        Wait until no job is running.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if all jobs finished in time.

        """
        if self._idle.is_set():
            return True
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True


async def run_apscheduler(
    scheduler: "BaseScheduler",
    stop_event: asyncio.Event | None = None,
    *,
    timeout: float | None = None,
) -> None:
    """
    Run a scheduler until the stop event, letting running jobs finish.

    Use it as (or inside) an app worker::

        async def worker(stop: asyncio.Event) -> None:
            scheduler = AsyncIOScheduler()
            scheduler.add_job(cleanup, "interval", minutes=5)
            await run_apscheduler(scheduler, stop)

    Args:
        scheduler: apscheduler ``AsyncIOScheduler`` (started here if not
            already running).
        stop_event: Event that ends the run. Defaults to the process stop
            event from :mod:`fastapi_mongo_base.core.lifecycle`.
        timeout: Seconds to wait for running jobs after the stop event.
            Defaults to ``BACKGROUND_SHUTDOWN_TIMEOUT``.

    """
    from apscheduler.events import (
        EVENT_JOB_ERROR,
        EVENT_JOB_EXECUTED,
        EVENT_JOB_SUBMITTED,
    )

    if stop_event is None:
        stop_event = lifecycle.get_stop_event()
    if timeout is None:
        timeout = project_settings.background_shutdown_timeout

    running = RunningJobs()
    scheduler.add_listener(running.on_submitted, EVENT_JOB_SUBMITTED)
    scheduler.add_listener(
        running.on_finished, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Scheduler started")
    try:
        await stop_event.wait()
        scheduler.pause()
        if running.count:
            logger.info("Waiting for %d scheduler job(s)", running.count)
        if not await running.wait_idle(timeout):
            logger.warning(
                "Cancelling %d scheduler job(s) after %ss",
                running.count,
                timeout,
            )
    finally:
        scheduler.shutdown(wait=False)
    # AsyncIOScheduler.shutdown() is scheduled on the loop; let it run.
    await asyncio.sleep(0)
    logger.info("Scheduler stopped")
