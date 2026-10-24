"""Tests for graceful shutdown: lifecycle, lifespan, serve and workers."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from fastapi_mongo_base.core import app_factory, lifecycle
from fastapi_mongo_base.core.config import Settings, project_settings
from fastapi_mongo_base.core.lifecycle import lifecycle as process_lifecycle

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture(autouse=True)
def enable_library_loggers() -> None:
    """Re-enable loggers that other tests' dictConfig calls may disable."""
    for name in (lifecycle.__name__, app_factory.__name__):
        logging.getLogger(name).disabled = False


def _settings(timeout: float = 5) -> SimpleNamespace:
    """
    Build settings with every datasource disabled.

    Args:
        timeout: Background shutdown timeout in seconds.

    Returns:
        Settings-like namespace accepted by ``lifespan``.

    """
    return SimpleNamespace(
        mongo_uri=None,
        redis_uri=None,
        database_uri=None,
        background_shutdown_timeout=timeout,
    )


# --- Lifecycle state ---


def test_begin_shutdown_sets_flag_and_event_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """begin_shutdown is idempotent and logs only the first call."""
    caplog.set_level(logging.INFO, logger=lifecycle.__name__)
    assert lifecycle.is_shutting_down() is False
    assert lifecycle.get_stop_event().is_set() is False

    process_lifecycle.begin_shutdown()
    process_lifecycle.begin_shutdown()

    assert lifecycle.is_shutting_down() is True
    assert lifecycle.get_stop_event().is_set() is True
    assert caplog.text.count("Shutdown started") == 1


async def test_spawn_tracks_task_until_done() -> None:
    """Spawned tasks are registered while running and removed after."""
    release = asyncio.Event()

    async def job() -> str:
        await release.wait()
        return "done"

    task = lifecycle.spawn(job(), name="job")
    assert task in process_lifecycle.tasks
    release.set()
    assert await task == "done"
    await asyncio.sleep(0)
    assert task not in process_lifecycle.tasks


async def test_spawn_logs_failure_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing spawned task is logged with its name."""

    async def boom() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("upload failed")

    task = lifecycle.spawn(boom(), name="upload")
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert "Background task upload failed" in caplog.text


async def test_spawn_during_shutdown_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Spawning after shutdown started still runs the task, with a warning."""
    process_lifecycle.begin_shutdown()

    async def late() -> int:
        await asyncio.sleep(0)
        return 1

    assert await lifecycle.spawn(late()) == 1
    assert "started during shutdown" in caplog.text


async def test_drain_waits_for_tasks_that_finish_in_time() -> None:
    """Drain waits for registered and extra tasks within the timeout."""
    finished: list[str] = []

    async def job(name: str) -> None:
        await asyncio.sleep(0.05)
        finished.append(name)

    lifecycle.spawn(job("registered"))
    extra = asyncio.create_task(job("extra"))
    await process_lifecycle.drain(1, extra=[extra])
    assert sorted(finished) == ["extra", "registered"]


async def test_drain_cancels_tasks_after_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tasks still running after the timeout are cancelled and named."""
    task = lifecycle.spawn(asyncio.sleep(60), name="slow-upload")
    started = time.monotonic()
    await process_lifecycle.drain(0.05)
    assert time.monotonic() - started < 2
    assert task.cancelled()
    assert "slow-upload" in caplog.text


async def test_drain_without_tasks_returns() -> None:
    """Drain is a no-op when nothing is running."""
    await process_lifecycle.drain(0)


async def test_cancel_and_wait_skips_finished_tasks() -> None:
    """cancel_and_wait cancels pending tasks and ignores finished ones."""
    done = asyncio.create_task(asyncio.sleep(0))
    await done
    pending = asyncio.create_task(asyncio.sleep(60))
    await lifecycle.cancel_and_wait([done, pending])
    assert pending.cancelled()
    assert not done.cancelled()
    await lifecycle.cancel_and_wait([])


def test_reset_returns_to_idle() -> None:
    """Reset clears the flag and replaces the stop event."""
    process_lifecycle.shutting_down = True
    process_lifecycle.reset()
    assert lifecycle.is_shutting_down() is False


@pytest.mark.parametrize(
    ("worker", "expected"),
    [
        (lambda: None, False),
        (lambda stop: stop, True),
        (lambda *args: args, True),
        (lambda *, stop: stop, False),
    ],
)
def test_worker_accepts_stop_event(worker: object, expected: object) -> None:
    """
    Workers opt in to the stop event with a positional parameter.

    Args:
        worker: Worker callable under test.
        expected: Whether it should receive the stop event.

    """
    assert lifecycle.worker_accepts_stop_event(worker) is expected


def test_worker_without_signature_is_legacy() -> None:
    """Callables without an inspectable signature are treated as legacy."""
    with patch.object(
        lifecycle.inspect, "signature", side_effect=ValueError("no sig")
    ):
        assert lifecycle.worker_accepts_stop_event(len) is False


# --- lifespan ---


async def test_lifespan_graceful_worker_and_shutdown_order() -> None:
    """Worker finishes its cycle, then shutdown functions, then datasources."""
    app = FastAPI()
    events: list[str] = []

    async def worker(stop: asyncio.Event) -> None:
        while not stop.is_set():
            events.append("cycle start")
            await asyncio.sleep(0.05)
            events.append("cycle done")
        events.append("worker stopped")

    async def close_client() -> None:
        await asyncio.sleep(0)
        events.append("close client")

    async def close_datasources(_app: FastAPI) -> None:
        await asyncio.sleep(0)
        events.append("datasources closed")

    with patch.object(
        app_factory, "_shutdown_datasources", side_effect=close_datasources
    ):
        async with app_factory.lifespan(
            app=app,
            worker=worker,
            settings=_settings(),
            shutdown_functions=[
                lambda: events.append("flush metrics"),
                close_client,
            ],
        ):
            await asyncio.sleep(0.01)
            assert app.state.worker is not None

    assert events[-5:] == [
        "cycle done",
        "worker stopped",
        "close client",
        "flush metrics",
        "datasources closed",
    ]
    assert app.state.worker.done()
    assert not app.state.worker.cancelled()


async def test_lifespan_legacy_worker_is_cancelled_immediately() -> None:
    """A zero-argument worker is cancelled at once, as before."""
    app = FastAPI()

    async def legacy_worker() -> None:
        await asyncio.sleep(60)

    started = time.monotonic()
    async with app_factory.lifespan(
        app=app, worker=legacy_worker, settings=_settings(timeout=30)
    ):
        await asyncio.sleep(0)
    assert time.monotonic() - started < 2
    assert app.state.worker.cancelled()


async def test_lifespan_graceful_worker_cancelled_after_timeout() -> None:
    """A stop-aware worker that does not return is cancelled on timeout."""
    app = FastAPI()

    async def stuck_worker(_stop: asyncio.Event) -> None:
        await asyncio.sleep(60)

    async with app_factory.lifespan(
        app=app, worker=stuck_worker, settings=_settings(timeout=0.05)
    ):
        await asyncio.sleep(0)
    assert app.state.worker.cancelled()


async def test_lifespan_non_coroutine_worker() -> None:
    """A worker that returns a non-coroutine leaves no task behind."""
    app = FastAPI()
    calls: list[str] = []

    async with app_factory.lifespan(
        app=app, worker=lambda: calls.append("ran"), settings=_settings()
    ):
        pass
    assert calls == ["ran"]
    assert app.state.worker is None


async def test_lifespan_waits_for_spawned_tasks() -> None:
    """Tasks spawned while serving finish before datasources close."""
    app = FastAPI()
    events: list[str] = []

    async def upload() -> None:
        await asyncio.sleep(0.05)
        events.append("upload done")

    async def close_datasources(_app: FastAPI) -> None:
        await asyncio.sleep(0)
        events.append("datasources closed")

    with patch.object(
        app_factory, "_shutdown_datasources", side_effect=close_datasources
    ):
        async with app_factory.lifespan(app=app, settings=_settings()):
            lifecycle.spawn(upload(), name="upload")
    assert events == ["upload done", "datasources closed"]


async def test_lifespan_failing_shutdown_function_does_not_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing shutdown function is logged; the rest still run."""
    app = FastAPI()
    events: list[str] = []

    def broken() -> None:
        raise RuntimeError("telegram down")

    async def close_datasources(_app: FastAPI) -> None:
        await asyncio.sleep(0)
        events.append("datasources closed")

    with patch.object(
        app_factory, "_shutdown_datasources", side_effect=close_datasources
    ):
        async with app_factory.lifespan(
            app=app,
            settings=_settings(),
            shutdown_functions=[lambda: events.append("first"), broken],
        ):
            pass
    assert events == ["first", "datasources closed"]
    assert "Shutdown function" in caplog.text


async def test_lifespan_without_settings_uses_default_timeout() -> None:
    """Without settings, the project default timeout is used."""
    app = FastAPI()
    with (
        patch.object(app_factory, "_startup_datasources"),
        patch.object(app_factory, "_shutdown_datasources"),
        patch.object(
            process_lifecycle, "drain", wraps=process_lifecycle.drain
        ) as drain,
    ):
        async with app_factory.lifespan(app=app):
            pass
    drain.assert_awaited_once_with(
        project_settings.background_shutdown_timeout
    )


async def test_create_app_wires_shutdown_functions() -> None:
    """create_app passes shutdown_functions through to the lifespan."""
    calls: list[str] = []
    app = app_factory.create_app(
        settings=Settings(),
        shutdown_functions=[lambda: calls.append("closed")],
    )
    with (
        patch.object(app_factory, "_startup_datasources"),
        patch.object(app_factory, "_shutdown_datasources"),
    ):
        async with app.router.lifespan_context(app):
            pass
    assert calls == ["closed"]


# --- readiness ---


async def test_readiness_reports_shutting_down() -> None:
    """Readiness returns 503 once shutdown started, before any checks."""
    app = FastAPI(version="2.0.0")
    app.state.datasources = {"mongodb": True}
    request = MagicMock()
    request.app = app
    process_lifecycle.begin_shutdown()
    with patch.object(app_factory.db, "check_mongodb") as check:
        response = await app_factory.readiness(request)
    assert response.status_code == 503
    assert b'"shutting_down"' in response.body
    assert b'"2.0.0"' in response.body
    check.assert_not_called()


async def test_readiness_shutting_down_without_version() -> None:
    """The shutting-down payload omits version when the app has none."""
    request = MagicMock()
    request.app.version = None
    process_lifecycle.begin_shutdown()
    response = await app_factory.readiness(request)
    assert response.status_code == 503
    assert b"version" not in response.body


# --- serve / GracefulServer ---


def test_build_server_uses_shutdown_timeout_setting() -> None:
    """The drain timeout defaults to SHUTDOWN_TIMEOUT and can be overridden."""
    default = lifecycle.build_server("main:app")
    assert default.config.timeout_graceful_shutdown == (
        project_settings.shutdown_timeout
    )
    assert default.config.host == "127.0.0.1"

    custom = lifecycle.build_server(
        "main:app", host="localhost", port=9000, shutdown_timeout=3
    )
    assert custom.config.timeout_graceful_shutdown == 3
    assert custom.config.port == 9000

    explicit = lifecycle.build_server("main:app", timeout_graceful_shutdown=7)
    assert explicit.config.timeout_graceful_shutdown == 7


def test_serve_runs_graceful_server() -> None:
    """serve() builds a GracefulServer and runs it."""
    with patch.object(lifecycle.GracefulServer, "run") as run:
        lifecycle.serve("main:app", port=9001)
    run.assert_called_once_with()


async def test_handle_exit_starts_shutdown() -> None:
    """The signal hook flips readiness and sets the stop event on the loop."""
    server = lifecycle.build_server("main:app")
    server._loop = asyncio.get_running_loop()
    server.handle_exit(signal.SIGTERM, None)
    assert server.should_exit is True
    assert lifecycle.is_shutting_down() is True
    await asyncio.sleep(0)
    assert lifecycle.get_stop_event().is_set()


def test_handle_exit_before_serve_only_sets_flag() -> None:
    """Before serve() there is no loop; the flag is still set."""
    server = lifecycle.build_server("main:app")
    server.handle_exit(signal.SIGTERM, None)
    assert server.should_exit is True
    assert lifecycle.is_shutting_down() is True


async def test_graceful_server_serve_records_loop() -> None:
    """GracefulServer.serve stores the running loop before serving."""
    server = lifecycle.build_server("main:app")
    with patch.object(lifecycle.uvicorn.Server, "serve") as parent_serve:
        await server.serve()
    assert server._loop is asyncio.get_running_loop()
    parent_serve.assert_awaited_once_with(None)


def _free_port() -> int:
    """
    Reserve a free local TCP port.

    Returns:
        Port number that was free a moment ago.

    """
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_for_port(port: int, timeout: float = 15) -> None:
    """
    Wait until a local TCP port accepts connections.

    Args:
        port: Port to poll.
        timeout: Maximum seconds to wait.

    Raises:
        TimeoutError: If the port never opens.

    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise TimeoutError(port)


SLOW_APP = """
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastapi_mongo_base.core.lifecycle import serve


@asynccontextmanager
async def lifespan(app):
    yield
    print("LIFESPAN SHUTDOWN", flush=True)


app = FastAPI(lifespan=lifespan)


@app.get("/slow")
async def slow():
    await asyncio.sleep(1.5)
    return {{"ok": True}}


if __name__ == "__main__":
    serve("slow_app:app", port={port}, shutdown_timeout=10)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
async def test_serve_sigterm_drains_in_flight_request(tmp_path: Path) -> None:
    """
    End to end: SIGTERM during a request still returns 200.

    Args:
        tmp_path: Temporary directory for the app module.

    """
    import httpx

    port = _free_port()
    (tmp_path / "slow_app.py").write_text(SLOW_APP.format(port=port))
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{SRC_DIR}"}
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(tmp_path / "slow_app.py"),
        cwd=tmp_path,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        await _wait_for_port(port)
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", timeout=10
        ) as client:
            request = asyncio.create_task(client.get("/slow"))
            await asyncio.sleep(0.4)
            proc.send_signal(signal.SIGTERM)
            response = await request
        output_bytes, _ = await asyncio.wait_for(proc.communicate(), 15)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    output = output_bytes.decode()
    assert response.status_code == 200, output
    assert "LIFESPAN SHUTDOWN" in output
    assert proc.returncode in {-signal.SIGTERM, 128 + signal.SIGTERM}


# --- run_worker ---


async def test_run_worker_returns_when_main_stops() -> None:
    """The worker sees the stop event and returns cleanly."""
    batches: list[int] = []

    async def main(stop: asyncio.Event) -> None:
        while not stop.is_set():
            batches.append(len(batches))
            if len(batches) == 3:
                process_lifecycle.begin_shutdown()
            await asyncio.sleep(0.01)

    await lifecycle.run_worker(main, timeout=1, signals=())
    assert batches == [0, 1, 2]


async def test_run_worker_handles_sigterm() -> None:
    """A real SIGTERM starts shutdown; the handler is removed afterwards."""
    committed: list[str] = []

    async def main(stop: asyncio.Event) -> None:
        os.kill(os.getpid(), signal.SIGTERM)
        await stop.wait()
        committed.append("batch")

    await lifecycle.run_worker(main, timeout=1)
    assert committed == ["batch"]
    loop = asyncio.get_running_loop()
    assert loop.remove_signal_handler(signal.SIGTERM) is False


async def test_run_worker_cancels_stuck_main() -> None:
    """A worker that ignores the stop event is cancelled after timeout."""
    cancelled: list[bool] = []

    async def main(_stop: asyncio.Event) -> None:
        process_lifecycle.begin_shutdown()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    await lifecycle.run_worker(main, timeout=0.05, signals=())
    assert cancelled == [True]


async def test_run_worker_propagates_crash() -> None:
    """A crash in the worker is re-raised for a non-zero exit."""

    async def main(_stop: asyncio.Event) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("redis gone")

    with pytest.raises(RuntimeError, match="redis gone"):
        await lifecycle.run_worker(main, signals=())


def test_run_worker_process_runs_to_completion() -> None:
    """The sync entrypoint runs the worker in a fresh event loop."""
    ran: list[str] = []

    async def main(_stop: asyncio.Event) -> None:
        await asyncio.sleep(0)
        ran.append("ran")

    lifecycle.run_worker_process(main, timeout=1)
    assert ran == ["ran"]


def test_config_logger_keeps_library_loggers_enabled() -> None:
    """Logging config must not disable loggers created at import."""
    Settings.config_logger()
    assert logging.getLogger(lifecycle.__name__).disabled is False
    assert logging.getLogger(app_factory.__name__).disabled is False
