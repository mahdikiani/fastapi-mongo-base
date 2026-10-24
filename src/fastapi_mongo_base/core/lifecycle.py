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
"""

import asyncio
import inspect
import logging
import signal
from collections.abc import Callable, Coroutine, Iterable
from types import FrameType
from typing import Any, TypeVar, cast

import uvicorn

from .config import project_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_HANDLED_SIGNALS = (signal.SIGINT, signal.SIGTERM)


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


async def cancel_and_wait(tasks: Iterable[asyncio.Task[Any]]) -> None:
    """
    Cancel tasks and wait until they have finished cancelling.

    Args:
        tasks: Tasks to cancel.

    """
    tasks = [task for task in tasks if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


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
    **uvicorn_kwargs: object,
) -> None:
    """
    Run a FastAPI app with graceful shutdown. Blocks until it stops.

    On SIGTERM/SIGINT: readiness turns 503 and workers get the stop event;
    uvicorn stops accepting connections and waits up to ``shutdown_timeout``
    for in-flight requests; the lifespan then waits for background tasks
    and closes datasources. A second Ctrl+C forces exit.

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
        **uvicorn_kwargs: Extra ``uvicorn.Config`` options.

    """
    build_server(
        app,
        host=host,
        port=port,
        shutdown_timeout=shutdown_timeout,
        **cast("Any", uvicorn_kwargs),
    ).run()


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
    signals = tuple(signals)
    for sig in signals:
        loop.add_signal_handler(sig, lifecycle.begin_shutdown)
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
        for sig in signals:
            loop.remove_signal_handler(sig)
    error = None if worker.cancelled() else worker.exception()
    if error is not None:
        raise error


def run_worker_process(
    main: Callable[[asyncio.Event], Coroutine[Any, Any, None]],
    *,
    timeout: float | None = None,
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

    """
    asyncio.run(run_worker(main, timeout=timeout))
