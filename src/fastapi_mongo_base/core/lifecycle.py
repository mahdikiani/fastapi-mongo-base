"""
Graceful shutdown: stop signal, background task registry and entrypoints.

One :class:`Lifecycle` exists per process (``lifecycle``). On SIGTERM or
SIGINT it flips readiness to 503, sets a stop event that workers watch, and
lets the application lifespan wait for registered background tasks before
datasources close.

Entrypoints:

- :func:`serve` runs a FastAPI app under uvicorn with a bounded HTTP drain.
- :func:`run_worker_process` runs a non-HTTP worker until it is signalled.

Background work:

- :func:`spawn` starts a task that shutdown waits for.
- :func:`get_stop_event` / :func:`is_shutting_down` let long-running code
  stop between units of work.

Nothing may keep the process alive forever: cancelled tasks get a bounded
time to finish cancelling (tasks that swallow ``CancelledError`` are logged
with their stack and abandoned), and both entrypoints run a
:class:`ShutdownWatchdog` thread that dumps every thread's stack and calls
``os._exit(1)`` if shutdown overruns, even when the event loop is blocked.
"""

import asyncio
import contextlib
import faulthandler
import inspect
import io
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable, Coroutine, Generator, Iterable
from types import FrameType
from typing import Any, TypeVar, cast

import uvicorn

from .config import project_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_HANDLED_SIGNALS = (signal.SIGINT, signal.SIGTERM)

CANCEL_TIMEOUT = 3.0
"""Seconds a cancelled task gets to finish cancelling before it is
abandoned (logged with its stack)."""

FORCE_EXIT_MARGIN = 2.0
"""Seconds added after the shutdown budget and :data:`CANCEL_TIMEOUT`
before the watchdog forces exit."""


class Lifecycle:
    """Process-wide shutdown state: stop event and background tasks."""

    def __init__(self) -> None:
        """Create an idle lifecycle (not shutting down, no tasks)."""
        self.shutting_down = False
        self._stop_event: asyncio.Event | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    @property
    def stop_event(self) -> asyncio.Event:
        """
        Event set when shutdown starts.

        Returns:
            The process stop event, created on first use.

        """
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        return self._stop_event

    @property
    def tasks(self) -> frozenset[asyncio.Task[Any]]:
        """
        Background tasks registered with :meth:`spawn` and still running.

        Returns:
            Snapshot of the running registered tasks.

        """
        return frozenset(self._tasks)

    def begin_shutdown(self) -> None:
        """Flip readiness and set the stop event. Safe to call twice."""
        if not self.shutting_down:
            logger.info("Shutdown started")
        self.shutting_down = True
        self.stop_event.set()

    def spawn(
        self,
        coro: Coroutine[Any, Any, T],
        *,
        name: str | None = None,
    ) -> asyncio.Task[T]:
        """
        Start a background task that shutdown waits for.

        The task is referenced until it finishes, so it cannot be garbage
        collected mid-flight. Its exception, if any, is logged.

        Args:
            coro: Coroutine to run.
            name: Task name, used in shutdown logs.

        Returns:
            The created task.

        """
        if self.shutting_down:
            logger.warning(
                "Background task %s started during shutdown",
                name or getattr(coro, "__qualname__", coro),
            )
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Background task %s failed",
                task.get_name(),
                exc_info=exc,
            )

    async def drain(
        self,
        timeout: float,
        extra: Iterable[asyncio.Task[Any]] = (),
    ) -> None:
        """
        Wait for registered tasks (and ``extra``), then cancel the rest.

        Args:
            timeout: Maximum seconds to wait before cancelling.
            extra: Additional tasks to wait for, such as the app worker.

        """
        pending = {task for task in (*self._tasks, *extra) if not task.done()}
        if not pending:
            return
        logger.info("Waiting for %d background task(s)", len(pending))
        _, still_running = await asyncio.wait(pending, timeout=timeout)
        if not still_running:
            return
        logger.warning(
            "Cancelling %d background task(s) after %ss: %s",
            len(still_running),
            timeout,
            sorted(task.get_name() for task in still_running),
        )
        await cancel_and_wait(still_running)

    def reset(self) -> None:
        """Return to the idle state. Intended for tests."""
        self.shutting_down = False
        self._stop_event = None
        self._tasks.clear()


lifecycle = Lifecycle()


def spawn(
    coro: Coroutine[Any, Any, T],
    *,
    name: str | None = None,
) -> asyncio.Task[T]:
    """
    Start a background task that graceful shutdown waits for.

    Use this instead of ``asyncio.create_task`` for fire-and-forget work
    started from request handlers (uploads, notifications, lookups).

    Args:
        coro: Coroutine to run.
        name: Task name, used in shutdown logs.

    Returns:
        The created task.

    """
    return lifecycle.spawn(coro, name=name)


def get_stop_event() -> asyncio.Event:
    """
    Get the event that is set when shutdown starts.

    Returns:
        The process stop event.

    """
    return lifecycle.stop_event


def is_shutting_down() -> bool:
    """
    Check whether shutdown has started.

    Returns:
        True once a stop signal was received or the lifespan is ending.

    """
    return lifecycle.shutting_down


def _task_stack(task: asyncio.Task[Any]) -> str:
    buffer = io.StringIO()
    task.print_stack(file=buffer)
    return buffer.getvalue()


async def cancel_and_wait(
    tasks: Iterable[asyncio.Task[Any]],
    timeout: float | None = None,
) -> set[asyncio.Task[Any]]:
    """
    Cancel tasks and wait (bounded) until they have finished cancelling.

    A task that catches ``CancelledError`` and keeps running would block a
    plain ``gather`` forever. Such tasks are logged with their stack and
    abandoned after ``timeout``.

    Args:
        tasks: Tasks to cancel.
        timeout: Seconds to wait for the cancellation to complete. Defaults
            to :data:`CANCEL_TIMEOUT`.

    Returns:
        Tasks that ignored the cancellation and are still running.

    """
    if timeout is None:
        timeout = CANCEL_TIMEOUT
    pending = {task for task in tasks if not task.done()}
    for task in pending:
        task.cancel()
    if not pending:
        return set()
    _, stubborn = await asyncio.wait(pending, timeout=timeout)
    for task in stubborn:
        logger.error(
            "Task %s ignored cancellation for %ss; abandoning it.\n%s",
            task.get_name(),
            timeout,
            _task_stack(task),
        )
    return stubborn


def worker_accepts_stop_event(worker: Callable[..., object]) -> bool:
    """
    Check whether a worker takes the stop event as its first argument.

    Args:
        worker: Worker callable.

    Returns:
        True if the worker declares at least one positional parameter.

    """
    try:
        parameters = inspect.signature(worker).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )
    return any(parameter.kind in positional for parameter in parameters)


class ShutdownWatchdog:
    """
    Force the process to exit if shutdown overruns its budget.

    A daemon thread polls ``lifecycle.shutting_down`` (a plain bool that
    signal handlers set directly), so it works even when the event loop is
    blocked by sync code. Once shutdown starts it allows ``after`` seconds,
    then logs, dumps every thread's stack to stderr and calls ``os._exit``.
    """

    def __init__(
        self,
        after: float,
        *,
        poll_interval: float = 0.2,
        exit_func: Callable[[int], object] = os._exit,
    ) -> None:
        """
        Configure the watchdog; :meth:`start` arms it.

        Args:
            after: Seconds allowed after shutdown starts. ``<= 0`` disables.
            poll_interval: Seconds between checks.
            exit_func: Called with exit code 1 on overrun.

        """
        self.after = after
        self.poll_interval = poll_interval
        self.exit_func = exit_func
        self.fired = False
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the watchdog thread (no-op if disabled or started)."""
        if self.after <= 0 or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="shutdown-watchdog", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Disarm the watchdog after a clean shutdown."""
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval * 5)

    def _run(self) -> None:
        while not lifecycle.shutting_down:
            if self._stopped.wait(self.poll_interval):
                return
        deadline = time.monotonic() + self.after
        while time.monotonic() < deadline:
            if self._stopped.wait(self.poll_interval):
                return
        self._fire()

    def _fire(self) -> None:
        self.fired = True
        logger.critical(
            "Shutdown did not finish within %ss; forcing exit. "
            "Thread stacks follow on stderr.",
            self.after,
        )
        with contextlib.suppress(Exception):
            faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        self.exit_func(1)


@contextlib.contextmanager
def shutdown_watchdog(
    after: float,
) -> Generator[ShutdownWatchdog, None, None]:
    """
    Run a :class:`ShutdownWatchdog` for the duration of the block.

    Args:
        after: Seconds allowed after shutdown starts. ``<= 0`` disables.

    Yields:
        The armed watchdog.

    """
    watchdog = ShutdownWatchdog(after)
    watchdog.start()
    try:
        yield watchdog
    finally:
        watchdog.stop()


def _force_exit_after(budget: float) -> float:
    configured = project_settings.shutdown_force_exit_after
    if configured is not None:
        return configured
    return budget + CANCEL_TIMEOUT + FORCE_EXIT_MARGIN


class GracefulServer(uvicorn.Server):
    """uvicorn server that also starts graceful shutdown on a signal."""

    _loop: asyncio.AbstractEventLoop | None = None

    async def serve(self, sockets: list | None = None) -> None:
        """
        Remember the running loop, then serve.

        Args:
            sockets: Optional pre-bound sockets, passed to uvicorn.

        """
        self._loop = asyncio.get_running_loop()
        await super().serve(sockets)

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        """
        Start graceful shutdown, then let uvicorn drain HTTP.

        Runs inside a signal handler, so it only sets a plain flag and
        schedules the rest on the event loop.

        Args:
            sig: Received signal number.
            frame: Current stack frame.

        """
        lifecycle.shutting_down = True
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(lifecycle.begin_shutdown)
        super().handle_exit(sig, frame)


def build_server(
    app: str | Callable[..., object],
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    shutdown_timeout: int | None = None,
    **uvicorn_kwargs: object,
) -> GracefulServer:
    """
    Build a uvicorn server with graceful shutdown.

    Args:
        app: ASGI app or import string such as ``"main:app"``.
        host: Bind address. Containers need ``"0.0.0.0"``.
        port: Bind port.
        shutdown_timeout: Max seconds to drain in-flight requests. Defaults
            to ``SHUTDOWN_TIMEOUT``.
        **uvicorn_kwargs: Extra ``uvicorn.Config`` options.

    Returns:
        Configured server, not started.

    """
    if shutdown_timeout is None:
        shutdown_timeout = project_settings.shutdown_timeout
    uvicorn_kwargs.setdefault("timeout_graceful_shutdown", shutdown_timeout)
    config = uvicorn.Config(
        app, host=host, port=port, **cast("Any", uvicorn_kwargs)
    )
    return GracefulServer(config)


def serve(
    app: str | Callable[..., object],
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    shutdown_timeout: int | None = None,
    force_exit_after: float | None = None,
    **uvicorn_kwargs: object,
) -> None:
    """
    Run a FastAPI app with graceful shutdown. Blocks until it stops.

    On SIGTERM/SIGINT: readiness turns 503 and workers get the stop event;
    uvicorn stops accepting connections and waits up to ``shutdown_timeout``
    for in-flight requests; the lifespan then waits for background tasks
    and closes datasources. A second Ctrl+C forces exit. If the whole
    shutdown takes longer than ``force_exit_after``, a watchdog dumps all
    thread stacks and exits with code 1, so a stuck worker can never keep
    the process alive.

    Example ``main.py``::

        from fastapi_mongo_base.core.lifecycle import serve
        from server.server import app

        if __name__ == "__main__":
            serve("main:app", host="0.0.0.0")

    Args:
        app: ASGI app or import string such as ``"main:app"``.
        host: Bind address. Containers need ``"0.0.0.0"``.
        port: Bind port.
        shutdown_timeout: Max seconds to drain in-flight requests. Defaults
            to ``SHUTDOWN_TIMEOUT``.
        force_exit_after: Seconds after the signal before the watchdog forces
            exit. Defaults to ``SHUTDOWN_FORCE_EXIT_AFTER``, else
            ``SHUTDOWN_TIMEOUT + BACKGROUND_SHUTDOWN_TIMEOUT + 5`` (35s). ``0``
            disables the watchdog.
        **uvicorn_kwargs: Extra ``uvicorn.Config`` options.

    """
    server = build_server(
        app,
        host=host,
        port=port,
        shutdown_timeout=shutdown_timeout,
        **cast("Any", uvicorn_kwargs),
    )
    if force_exit_after is None:
        force_exit_after = _force_exit_after(
            (server.config.timeout_graceful_shutdown or 0)
            + project_settings.background_shutdown_timeout
        )
    with shutdown_watchdog(force_exit_after):
        server.run()


async def run_worker(
    main: Callable[[asyncio.Event], Coroutine[Any, Any, None]],
    *,
    timeout: float | None = None,
    signals: Iterable[signal.Signals] = _HANDLED_SIGNALS,
) -> None:
    """
    Run ``main(stop_event)`` until it returns or a signal stops it.

    After a signal, ``main`` gets up to ``timeout`` seconds to finish its
    current unit of work and return; then it is cancelled.

    Args:
        main: Worker coroutine function. Receives the stop event.
        timeout: Seconds to wait after the signal. Defaults to
            ``BACKGROUND_SHUTDOWN_TIMEOUT``.
        signals: Signals that start shutdown.

    """
    if timeout is None:
        timeout = project_settings.background_shutdown_timeout
    loop = asyncio.get_running_loop()

    def on_signal(_sig: int, _frame: FrameType | None) -> None:
        # signal.signal (not loop.add_signal_handler) so the flag is set even
        # while sync code blocks the loop; the watchdog thread reads it.
        lifecycle.shutting_down = True
        if not loop.is_closed():
            loop.call_soon_threadsafe(lifecycle.begin_shutdown)

    previous = {sig: signal.signal(sig, on_signal) for sig in signals}
    stop_event = lifecycle.stop_event
    worker = asyncio.create_task(main(stop_event), name="worker")
    stop_wait = asyncio.create_task(stop_event.wait(), name="stop-wait")
    try:
        await asyncio.wait(
            {worker, stop_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        await lifecycle.drain(timeout, extra=[worker])
    finally:
        await cancel_and_wait([stop_wait, worker])
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    if not worker.done():
        logger.error("Worker ignored cancellation; exiting without it")
        return
    error = None if worker.cancelled() else worker.exception()
    if error is not None:
        raise error


def run_worker_process(
    main: Callable[[asyncio.Event], Coroutine[Any, Any, None]],
    *,
    timeout: float | None = None,
    force_exit_after: float | None = None,
) -> None:
    """
    Entrypoint for a non-HTTP worker process. Blocks until it stops.

    Example::

        async def consume(stop: asyncio.Event) -> None:
            while not stop.is_set():
                await process_one_batch()

        if __name__ == "__main__":
            run_worker_process(consume)

    Args:
        main: Worker coroutine function. Receives the stop event.
        timeout: Seconds to wait after the signal. Defaults to
            ``BACKGROUND_SHUTDOWN_TIMEOUT``.
        force_exit_after: Seconds after the signal before the watchdog forces
            exit (stack dump, exit code 1). Defaults to
            ``SHUTDOWN_FORCE_EXIT_AFTER``, else ``timeout + 5`` (15s). ``0``
            disables the watchdog.

    """
    if timeout is None:
        timeout = project_settings.background_shutdown_timeout
    if force_exit_after is None:
        force_exit_after = _force_exit_after(timeout)
    with shutdown_watchdog(force_exit_after):
        asyncio.run(run_worker(main, timeout=timeout))
