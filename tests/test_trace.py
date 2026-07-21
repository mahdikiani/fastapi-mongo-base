"""Tests for request trace ID middleware, helpers, and log enrichment."""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
import json_advanced as json
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.fastapi_mongo_base.core.app_factory import setup_middlewares
from src.fastapi_mongo_base.logging.formatters import JsonFormatter
from src.fastapi_mongo_base.middlewares.trace import TraceMiddleware
from src.fastapi_mongo_base.utils import trace as trace_util


def test_middlewares_package_exports_trace() -> None:
    """Public middleware package should export TraceMiddleware."""
    from src.fastapi_mongo_base import middlewares

    assert "TraceMiddleware" in middlewares.__all__
    assert middlewares.TraceMiddleware is TraceMiddleware


def test_generate_trace_id_returns_uuid7_string() -> None:
    """generate_trace_id should return a parseable UUID string."""
    value = trace_util.generate_trace_id()
    assert UUID(value).version == 7


def test_get_trace_id_defaults_to_none() -> None:
    """Outside a request, get_trace_id should be unset."""
    assert trace_util.get_trace_id() is None


def test_get_trace_headers_empty_without_context() -> None:
    """get_trace_headers should return {} when no trace is bound."""
    assert trace_util.get_trace_headers() == {}


def test_get_trace_headers_includes_bound_trace_id() -> None:
    """get_trace_headers should expose X-Trace-ID for outbound calls."""
    token = trace_util.request_trace_id.set("trace-abc")
    try:
        assert trace_util.get_trace_headers() == {
            trace_util.TRACE_ID_HEADER: "trace-abc",
        }
        assert trace_util.get_trace_id() == "trace-abc"
    finally:
        trace_util.request_trace_id.reset(token)


def test_trace_middleware_generates_and_echoes_trace_id() -> None:
    """Missing inbound header should yield a generated UUID7 on response."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)
    seen: dict[str, str | None] = {}

    @app.get("/ping")
    async def ping(request: Request) -> dict[str, str | None]:
        seen["state"] = getattr(request.state, "trace_id", None)
        seen["context"] = trace_util.get_trace_id()
        return {"ok": "true"}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    trace_id = response.headers[trace_util.TRACE_ID_HEADER.lower()]
    assert UUID(trace_id).version == 7
    assert seen["state"] == trace_id
    assert seen["context"] == trace_id
    assert trace_util.get_trace_id() is None


def test_trace_middleware_propagates_inbound_trace_id() -> None:
    """Inbound X-Trace-ID should be preserved end-to-end."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)
    inbound = "0193e4c8-7b2a-7f3c-9d1e-2a4b6c8d0e1f"
    seen: dict[str, str | None] = {}

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        seen["context"] = trace_util.get_trace_id()
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get(
            "/ping",
            headers={trace_util.TRACE_ID_HEADER: inbound},
        )

    assert response.status_code == 200
    assert response.headers[trace_util.TRACE_ID_HEADER.lower()] == inbound
    assert seen["context"] == inbound


def test_trace_middleware_treats_blank_header_as_missing() -> None:
    """Blank X-Trace-ID should be replaced with a generated value."""
    app = FastAPI()
    app.add_middleware(TraceMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get(
            "/ping",
            headers={trace_util.TRACE_ID_HEADER: "  "},
        )

    assert response.status_code == 200
    trace_id = response.headers[trace_util.TRACE_ID_HEADER.lower()]
    assert trace_id.strip()
    assert UUID(trace_id).version == 7


def test_json_formatter_includes_trace_id_when_bound() -> None:
    """JsonFormatter should enrich records with the active trace_id."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    token = trace_util.request_trace_id.set("trace-log-1")
    try:
        payload = json.loads(formatter.format(record))
    finally:
        trace_util.request_trace_id.reset(token)

    assert payload["message"] == "hello"
    assert payload["trace_id"] == "trace-log-1"


def test_json_formatter_omits_trace_id_when_unbound() -> None:
    """JsonFormatter should omit trace_id outside a request context."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert "trace_id" not in payload


def test_setup_middlewares_registers_trace_by_default() -> None:
    """setup_middlewares should enable TraceMiddleware unless disabled."""
    app = FastAPI()
    setup_middlewares(app=app)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    assert trace_util.TRACE_ID_HEADER.lower() in response.headers


def test_setup_middlewares_can_disable_trace() -> None:
    """trace_middleware=False should skip TraceMiddleware registration."""
    app = FastAPI()
    setup_middlewares(app=app, trace_middleware=False)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    assert trace_util.TRACE_ID_HEADER.lower() not in response.headers


def _capture_transport(
    captured: dict[str, object],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["header"] = request.headers.get(trace_util.TRACE_ID_HEADER)
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


def test_create_client_injects_trace_header() -> None:
    """create_client should inject the active trace ID automatically."""
    captured: dict[str, object] = {}
    token = trace_util.request_trace_id.set("trace-httpx-1")
    try:
        with trace_util.create_client(
            transport=_capture_transport(captured),
        ) as client:
            response = client.get("https://example.test/ping")
    finally:
        trace_util.request_trace_id.reset(token)

    assert response.status_code == 200
    assert captured["header"] == "trace-httpx-1"


def test_create_client_does_not_overwrite_explicit_header() -> None:
    """Explicit X-Trace-ID on the request should win over context."""
    captured: dict[str, object] = {}
    token = trace_util.request_trace_id.set("trace-context")
    try:
        with trace_util.create_client(
            transport=_capture_transport(captured),
        ) as client:
            client.get(
                "https://example.test/ping",
                headers={trace_util.TRACE_ID_HEADER: "trace-explicit"},
            )
    finally:
        trace_util.request_trace_id.reset(token)

    assert captured["header"] == "trace-explicit"


def test_create_client_skips_header_without_trace() -> None:
    """Without a bound trace, create_client should not add X-Trace-ID."""
    captured: dict[str, object] = {}
    with trace_util.create_client(
        transport=_capture_transport(captured),
    ) as client:
        client.get("https://example.test/ping")

    assert captured["header"] is None


@pytest.mark.asyncio
async def test_create_async_client_injects_trace_header() -> None:
    """create_async_client should inject the active trace ID."""
    captured: dict[str, object] = {}
    token = trace_util.request_trace_id.set("trace-async-1")
    try:
        async with trace_util.create_async_client(
            transport=_capture_transport(captured),
        ) as client:
            response = await client.get("https://example.test/ping")
    finally:
        trace_util.request_trace_id.reset(token)

    assert response.status_code == 200
    assert captured["header"] == "trace-async-1"


@pytest.mark.asyncio
async def test_traced_async_client_injects_trace_header() -> None:
    """TracedAsyncClient should behave like create_async_client."""
    captured: dict[str, object] = {}
    token = trace_util.request_trace_id.set("trace-subclass-1")
    try:
        async with trace_util.TracedAsyncClient(
            transport=_capture_transport(captured),
        ) as client:
            await client.get("https://example.test/ping")
    finally:
        trace_util.request_trace_id.reset(token)

    assert captured["header"] == "trace-subclass-1"


def test_install_trace_on_existing_client() -> None:
    """install_trace should wire injection onto an existing client."""
    captured: dict[str, object] = {}
    client = httpx.Client(transport=_capture_transport(captured))
    trace_util.install_trace(client)
    token = trace_util.request_trace_id.set("trace-install-1")
    try:
        with client:
            client.get("https://example.test/ping")
    finally:
        trace_util.request_trace_id.reset(token)

    assert captured["header"] == "trace-install-1"


def test_merge_trace_event_hooks_is_idempotent() -> None:
    """merge_trace_event_hooks should not duplicate the inject hook."""
    once = trace_util.merge_trace_event_hooks()
    twice = trace_util.merge_trace_event_hooks(once)
    assert twice["request"].count(trace_util.inject_trace_header) == 1

    async_once = trace_util.merge_trace_event_hooks(is_async=True)
    async_twice = trace_util.merge_trace_event_hooks(
        async_once,
        is_async=True,
    )
    assert async_twice["request"].count(
        trace_util.ainject_trace_header,
    ) == 1


@pytest.mark.asyncio
async def test_install_trace_on_async_client() -> None:
    """install_trace should use the async hook for AsyncClient."""
    captured: dict[str, object] = {}
    client = httpx.AsyncClient(transport=_capture_transport(captured))
    trace_util.install_trace(client)
    token = trace_util.request_trace_id.set("trace-install-async")
    try:
        async with client:
            await client.get("https://example.test/ping")
    finally:
        trace_util.request_trace_id.reset(token)

    assert captured["header"] == "trace-install-async"
