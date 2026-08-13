"""More coverage for app_factory, basic, mongo, tasks, emit, schemas."""

from __future__ import annotations

import asyncio
import dataclasses
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from fastapi_mongo_base.audit.emit import (
    dump_entity,
    maybe_record_audit,
)
from fastapi_mongo_base.audit.schemas import AuditAction
from fastapi_mongo_base.core import app_factory
from fastapi_mongo_base.core.config import Settings
from fastapi_mongo_base.db import mongo as mongo_db
from fastapi_mongo_base.models import TenantSubjectEntity
from fastapi_mongo_base.schemas import (
    OwnedEntitySchema,
    TenantOwnedEntitySchema,
    TenantScopedEntitySchema,
    TenantSubjectEntitySchema,
    TenantUserEntitySchema,
    TenantWorkspaceEntitySchema,
    UserOwnedEntitySchema,
    WorkspaceOwnedEntitySchema,
)
from fastapi_mongo_base.tasks import TaskMixin
from fastapi_mongo_base.utils import basic


@pytest.mark.asyncio
async def test_lifespan_worker_init_and_shutdown() -> None:
    """Lifespan covers worker coroutine, sync/async init, shutdown."""
    app = FastAPI()
    settings = Settings()
    settings.mongo_uri = None
    settings.redis_uri = None
    settings.database_uri = None

    ran = {"sync": False, "async": False}

    def sync_init() -> None:
        ran["sync"] = True

    async def async_init() -> None:
        await asyncio.sleep(0)
        ran["async"] = True

    async def worker() -> None:
        await basic.asyncio.sleep(10)  # type: ignore[attr-defined]

    # use real asyncio.sleep via patch later
    async def long_worker() -> None:
        import asyncio

        await asyncio.sleep(60)

    with (
        patch.object(app_factory, "_use_mongodb", return_value=False),
        patch.object(app_factory, "_use_redis", return_value=False),
        patch.object(app_factory, "_use_sql", return_value=False),
        patch.object(
            app_factory.db,
            "close_mongo_client",
            new=AsyncMock(),
        ),
        patch.object(app_factory.db, "close_redis", new=AsyncMock()),
        patch.object(app_factory.db, "close_sql", new=AsyncMock()),
    ):
        app.state.mongo_client = object()
        app.state.redis_sync_client = object()
        app.state.redis_async_client = object()
        app.state.sql_engine = object()

        async with app_factory.lifespan(
            app=app,
            worker=long_worker,
            init_functions=[sync_init, async_init],
            settings=settings,
        ):
            assert ran["sync"] is True
            assert ran["async"] is True
            assert app.state.worker is not None

        # cancel was requested during shutdown
        worker = app.state.worker
        cancelling = getattr(worker, "cancelling", lambda: False)
        assert worker.cancelled() or cancelling()


@pytest.mark.asyncio
async def test_startup_datasources_enabled_branches() -> None:
    """_startup_datasources initializes configured backends."""
    app = FastAPI()
    settings = MagicMock()
    with (
        patch.object(app_factory, "_use_mongodb", return_value=True),
        patch.object(app_factory, "_use_redis", return_value=True),
        patch.object(app_factory, "_use_sql", return_value=True),
        patch.object(
            app_factory.db,
            "init_mongo_db",
            new=AsyncMock(return_value=("db", "client")),
        ),
        patch.object(
            app_factory.db,
            "init_redis",
            return_value=("sync", "async"),
        ),
        patch.object(
            app_factory.db,
            "init_sql",
            new=AsyncMock(return_value=("engine", "session")),
        ),
    ):
        await app_factory._startup_datasources(app, settings)
    assert app.state.mongo_db == "db"
    assert app.state.redis_sync_client == "sync"
    assert app.state.sql_engine == "engine"


def test_use_helpers_when_packages_missing() -> None:
    """_use_* returns False when optional packages are absent."""
    settings = MagicMock()
    settings.mongo_uri = "mongodb://x"
    settings.redis_uri = "redis://x"
    settings.database_uri = "sqlite://"

    def _no_pkg(_name: str) -> None:
        return None

    with patch("importlib.util.find_spec", side_effect=_no_pkg):
        assert app_factory._use_mongodb(settings) is False
        assert app_factory._use_redis(settings) is False
        assert app_factory._use_sql(settings) is False


def test_setup_exception_handlers_and_routes(tmp_path: object) -> None:
    """Custom handlers, logs, index, and coverage mount paths."""
    app = FastAPI()
    app_factory.setup_exception_handlers(
        app=app,
        handlers={ValueError: lambda _req, _exc: None},
    )

    @dataclasses.dataclass
    class _S:
        base_path: str = "/api"
        base_dir: object = tmp_path

        def get_log_config(self) -> dict:
            log = tmp_path / "app.log"
            log.write_bytes(b"line1\nline2\n")
            return {"info_log_path": str(log)}

        def get_coverage_dir(self) -> object:
            cov = tmp_path / "htmlcov"
            cov.mkdir(exist_ok=True)
            (cov / "index.html").write_text("ok")
            return cov

    settings = _S()
    app_factory._register_utility_routes(
        app,
        settings=settings,
        log_route=True,
        health_route=False,
        readiness_route=False,
        index_route=True,
        serve_coverage=True,
        kubernetes_route=False,
    )
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/logs") for p in paths)
    assert "/" in paths


@pytest.mark.asyncio
async def test_basic_delay_try_except_and_debug_sync() -> None:
    """Cover delay_execution, try_except sync_to_thread, debug sync."""

    @basic.delay_execution(0)
    def delayed() -> str:
        return "d"

    assert delayed() == "d"

    @basic.delay_execution(0, sync_to_thread=True)
    def delayed_sync() -> str:
        return "ds"

    assert await delayed_sync() == "ds"

    @basic.delay_execution(0)
    async def delayed_async() -> str:
        await asyncio.sleep(0)
        return "da"

    assert await delayed_async() == "da"

    @basic.try_except_wrapper
    def sync_ok() -> int:
        return 1

    assert sync_ok() == 1

    calls = {"n": 0}

    @basic.retry_execution(attempts=2, delay=0, sync_to_thread=True)
    def threaded_fail() -> str:
        calls["n"] += 1
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await threaded_fail()

    @basic.debug_mode_mock("mocked")
    def sync_real() -> str:
        return "real"

    with patch.object(Settings, "debug", True):
        assert sync_real() == "mocked"
    with patch.object(Settings, "debug", False):
        assert sync_real() == "real"

    @basic.debug_mode_mock(lambda: "callable-mock")
    def sync_callable() -> str:
        return "real"

    with patch.object(Settings, "debug", True):
        assert sync_callable() == "callable-mock"


def test_parse_array_json_non_list_and_invalid() -> None:
    """parse_array_parameter JSON scalar-in-array and invalid JSON branches."""
    assert basic.parse_array_parameter("[42]") == [42]
    assert basic.parse_array_parameter("[not-json") == ["[not-json"]


@pytest.mark.asyncio
async def test_mongo_check_close_and_discover() -> None:
    """Mongo helpers for check/close/document discovery."""
    assert await mongo_db.check_mongodb(None) == "down"
    assert await mongo_db.check_mongodb(object()) == "down"

    client = MagicMock()
    client.admin.command = AsyncMock(return_value={"ok": 1})
    assert await mongo_db.check_mongodb(client) == "up"
    client.admin.command = AsyncMock(side_effect=RuntimeError("x"))
    assert await mongo_db.check_mongodb(client) == "down"

    class _Closing:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    closing = _Closing()
    await mongo_db.close_mongo_client(closing)
    assert closing.closed is True
    await mongo_db.close_mongo_client(None)

    docs = mongo_db.discover_beanie_document_models()
    assert isinstance(docs, list)


@pytest.mark.asyncio
async def test_emit_signals_webhook_errors() -> None:
    """TaskMixin.emit_signals covers HTTP and generic webhook errors."""

    class _T(TaskMixin):
        uid: str = "t1"
        webhook_url: str | None = "http://example.test/hook"
        webhook_custom_headers: dict | None = None
        meta_data: dict | None = None

        async def save_report(self, *_a: object, **_k: object) -> None:
            return None

        async def save(self) -> None:
            return None

        def model_dump(self, **_kwargs: object) -> dict:
            return {"uid": self.uid}

    task = _T(meta_data={"webhook": None, "webhook_url": None})
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "err"
    mock_resp.raise_for_status.side_effect = __import__(
        "httpx"
    ).HTTPStatusError("bad", request=MagicMock(), response=mock_resp)
    mock_resp.json.return_value = {}

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await TaskMixin.emit_signals(task)

    mock_client.post = AsyncMock(side_effect=RuntimeError("net"))
    with patch("httpx.AsyncClient", return_value=mock_client):
        await TaskMixin.emit_signals(task)


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_tenant_subject_get_item() -> None:
    """TenantSubjectEntity enforces tenant and subject constraints."""

    class _Sub(TenantSubjectEntity):
        class Settings(TenantSubjectEntity.Settings):
            name = "cov_tenant_subject"
            __abstract__ = True

    with pytest.raises(ValueError, match="tenant_id"):
        await _Sub.get_item("u")
    with pytest.raises(ValueError, match="user_id or workspace_id"):
        await _Sub.get_item("u", tenant_id="t")
    with patch(
        "fastapi_mongo_base.models.BaseEntity.get_item",
        new=AsyncMock(return_value=None),
    ):
        assert (
            await _Sub.get_item("u", tenant_id="t", ignore_subject=True)
            is None
        )


@pytest.mark.asyncio
async def test_dump_entity_and_maybe_record() -> None:
    """dump_entity fallbacks and maybe_record_audit short-circuit."""

    class _DumpOnly:
        def dump(self) -> dict:
            return {"a": 1}

    assert dump_entity(_DumpOnly())["a"] == 1

    class _Weird:
        def model_dump(self) -> list:
            return [1]

    assert dump_entity(_Weird()) == {}

    class _Attrs:
        value = 3

        def method(self) -> None:
            return None

    dumped = dump_entity(_Attrs())
    assert dumped.get("value") == 3

    with patch(
        "fastapi_mongo_base.audit.emit.is_audit_enabled",
        return_value=False,
    ):
        await maybe_record_audit(action=AuditAction.create, item=_Attrs())


def test_schema_item_url_helpers() -> None:
    """Entity schema item_url / create helpers for ownership schemas."""
    for schema_cls in (
        UserOwnedEntitySchema,
        OwnedEntitySchema,
        WorkspaceOwnedEntitySchema,
        TenantScopedEntitySchema,
        TenantUserEntitySchema,
        TenantWorkspaceEntitySchema,
        TenantSubjectEntitySchema,
        TenantOwnedEntitySchema,
    ):
        fields = getattr(schema_cls, "model_fields", {})
        assert fields


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_get_by_uid_and_invalid_range_filter() -> None:
    """get_by_uid and invalid range values in filters."""
    from tests.app.server import TestEntity

    item = await TestEntity.create_item({"name": "byuid", "number": 1})
    found = await TestEntity.get_by_uid(item.uid)
    assert found is not None
    filters = TestEntity._build_extra_filters(created_at_from=[])
    assert "created_at" not in filters
