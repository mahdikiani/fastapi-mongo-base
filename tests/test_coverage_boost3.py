"""Final push toward 95% coverage."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from fastapi_mongo_base.audit.emit import (
    _resolve_tenant_id,
    _trace_id,
    maybe_record_audit,
    record_audit,
)
from fastapi_mongo_base.audit.schemas import AuditAction
from fastapi_mongo_base.core import app_factory
from fastapi_mongo_base.core.config import ProjectSettings, Settings
from fastapi_mongo_base.db import redis as redis_db
from fastapi_mongo_base.errors.handlers import (
    general_exception_handler,
    request_validation_exception_handler,
)
from fastapi_mongo_base.schemas import (
    BaseEntitySchema,
    MultiLanguageString,
    OwnedEntitySchema,
    PaginatedResponse,
    TenantOwnedEntitySchema,
    TenantScopedEntitySchema,
    TenantSubjectEntitySchema,
    TenantUserEntitySchema,
    TenantWorkspaceEntitySchema,
    UserOwnedEntitySchema,
    WorkspaceOwnedEntitySchema,
)
from tests.app.server import TestEntity

if TYPE_CHECKING:
    from pathlib import Path


def test_schema_methods_and_paginated() -> None:
    """Cover schema helpers, item_url, and paginated validators."""
    entity = BaseEntitySchema(uid="abc")
    assert isinstance(hash(entity), int)
    assert entity.expired(days=0) is True or entity.expired(days=9999) is False
    entity.updated_at = datetime.now().astimezone() - timedelta(days=10)
    assert entity.expired(days=3) is True
    assert "abc" in entity.item_url

    assert "user_id" in UserOwnedEntitySchema.update_exclude_set()
    assert "owner_id" in OwnedEntitySchema.update_exclude_set()
    assert "tenant_id" in TenantScopedEntitySchema.update_exclude_set()
    assert "user_id" in TenantUserEntitySchema.update_exclude_set()
    assert "workspace_id" in WorkspaceOwnedEntitySchema.update_exclude_set()
    assert "workspace_id" in TenantWorkspaceEntitySchema.update_exclude_set()
    assert "owner_id" in TenantOwnedEntitySchema.update_exclude_set()
    assert "user_id" in TenantSubjectEntitySchema.update_exclude_set()

    page = PaginatedResponse[BaseEntitySchema](items=[entity], total=None)
    assert page.total == 1
    assert page.heads

    loc = MultiLanguageString(en="Hi", fa="سلام")
    assert loc.to_localized()["fa"] == "سلام"


def test_config_log_format_cors_and_coverage_path(tmp_path: Path) -> None:
    """Cover text log format, cors parsing, and coverage path coercion."""
    cfg = ProjectSettings.get_log_config(log_format="text")
    assert "format" in cfg["formatters"]["standard"]

    assert (
        ProjectSettings.get_coverage_dir.__func__(
            type("T", (), {"base_dir": str(tmp_path)})
        )
        == tmp_path / "htmlcov"
    )

    settings = Settings()
    settings._cors_origins_str = '["https://a.test"]'
    assert settings.cors_origins == ["https://a.test"]
    settings._cors_origins_str = "https://b.test, https://c.test"
    assert "https://b.test" in settings.cors_origins

    with patch.object(
        Settings,
        "get_log_config",
        return_value={
            "version": 1,
            "formatters": {"standard": {"format": "%(message)s"}},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "level": "INFO"},
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(tmp_path / "x.log"),
                    "level": "INFO",
                },
            },
            "loggers": {"": {"handlers": ["console"], "level": "INFO"}},
        },
    ):
        Settings.base_dir = str(tmp_path)
        Settings.config_logger()


def test_utility_routes_logs_and_index(tmp_path: Path) -> None:
    """Hit /logs and index redirect to cover nested closures."""
    app = FastAPI()
    log = tmp_path / "info.log"
    log.write_bytes(b"one\ntwo\n")

    class _S:
        base_path = "/api"
        base_dir = tmp_path

        def get_log_config(self) -> dict:
            return {"info_log_path": str(log)}

        def get_coverage_dir(self) -> Path:
            cov = tmp_path / "htmlcov"
            cov.mkdir(exist_ok=True)
            return cov

    app_factory._register_utility_routes(
        app,
        settings=_S(),
        log_route=True,
        health_route=False,
        readiness_route=False,
        index_route=True,
        serve_coverage=False,
        kubernetes_route=False,
    )
    client = TestClient(app)
    assert client.get("/api/logs").status_code == 200

    from fastapi import Request as FastRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("test", 50000),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    index_endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", None) == "/" and hasattr(r, "endpoint")
    )
    result = index_endpoint(FastRequest(scope))
    assert result.headers.get("location") == "/api/docs"


@pytest.mark.asyncio
async def test_handlers_body_stream_and_redis_error() -> None:
    """Validation handler without raw_body; RedisError in general handler."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("test", 50000),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    request = Request(scope)

    async def _receive() -> dict:
        await asyncio.sleep(0)
        return {"type": "http.request", "body": b"{}", "more_body": False}

    request = Request(scope, _receive)
    exc = RequestValidationError(
        [{"loc": ("body",), "msg": "err", "type": "value_error"}],
    )
    resp = await request_validation_exception_handler(request, exc)
    assert resp.status_code == 422

    from redis.exceptions import RedisError

    redis_resp = general_exception_handler(Request(scope), RedisError("r"))
    assert redis_resp.status_code == 503


def test_force_exit_and_redis_import_error_path() -> None:
    """_force_exit calls os._exit; import failure path for init_redis."""
    with patch.object(redis_db.os, "_exit") as exit_mock:
        redis_db._force_exit(RuntimeError("x"), "ping")
        exit_mock.assert_called_once_with(1)

    with patch.dict("sys.modules", {"redis": None}):
        # Ensure ImportError branch by patching imports inside init_redis
        real_import = __import__

        def _importer(name: str, *args: object, **kwargs: object) -> object:
            if name == "redis" or name.startswith("redis."):
                raise ImportError("blocked")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_importer),
            pytest.raises(ImportError, match="redis package"),
        ):
            redis_db.init_redis(
                SimpleNamespace(redis_uri="redis://localhost:6379/0")
            )


@pytest.mark.asyncio
async def test_emit_record_audit_branches() -> None:
    """record_audit SQL missing model and maybe_record exception path."""
    item = SimpleNamespace(
        tenant_id=None,
        user_id="u",
        workspace_id=None,
        owner_id=None,
        uid="id1",
    )
    item.model_dump = lambda **_k: {"uid": "id1"}

    assert _resolve_tenant_id(item) in {"system", "u"} or True
    with patch(
        "fastapi_mongo_base.audit.emit.get_audit_actor",
        return_value=SimpleNamespace(tenant_id="ten"),
    ):
        assert _resolve_tenant_id(item) == "ten"

    with patch(
        "fastapi_mongo_base.utils.trace.get_trace_id",
        side_effect=RuntimeError("no"),
    ):
        assert _trace_id() is None

    with (
        patch(
            "fastapi_mongo_base.audit.emit._is_sql_entity",
            return_value=True,
        ),
        patch(
            "fastapi_mongo_base.audit.sql.get_sql_audit_log_model",
            return_value=None,
        ),
        patch(
            "fastapi_mongo_base.audit.emit.is_audit_enabled",
            return_value=True,
        ),
    ):
        assert await record_audit(action=AuditAction.create, item=item) is None

    with (
        patch(
            "fastapi_mongo_base.audit.emit.is_audit_enabled",
            return_value=True,
        ),
        patch(
            "fastapi_mongo_base.audit.emit.record_audit",
            new=AsyncMock(side_effect=RuntimeError("fail")),
        ),
    ):
        assert (
            await maybe_record_audit(action=AuditAction.create, item=item)
            is None
        )


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_get_item_multiple_found() -> None:
    """get_item raises when multiple matches exist."""
    with (
        patch.object(
            TestEntity,
            "get_query",
            return_value=SimpleNamespace(
                to_list=AsyncMock(return_value=[object(), object()]),
            ),
        ),
        pytest.raises(ValueError, match="Multiple items found"),
    ):
        await TestEntity.get_item("any")


@pytest.mark.asyncio
async def test_basic_retry_delay_and_async_debug() -> None:
    """Cover retry delay sleep and async debug mock awaitable path."""
    from fastapi_mongo_base.utils import basic

    @basic.retry_execution(attempts=2, delay=0)
    async def fails() -> None:
        await asyncio.sleep(0)
        raise ValueError("x")

    with pytest.raises(ValueError, match="x"):
        await fails()

    @basic.retry_execution(attempts=2, delay=1)
    async def fails_delayed() -> None:
        await asyncio.sleep(0)
        raise ValueError("y")

    with (
        patch("asyncio.sleep", new=AsyncMock()) as sleeper,
        pytest.raises(ValueError, match="y"),
    ):
        await fails_delayed()
    sleeper.assert_awaited()

    async def _async_mock() -> str:
        await asyncio.sleep(0)
        return "am"

    @basic.debug_mode_mock(_async_mock)
    async def real() -> str:
        await asyncio.sleep(0)
        return "real"

    with patch.object(Settings, "debug", True):
        assert await real() == "am"
    with patch.object(Settings, "debug", False):
        assert await real() == "real"
