"""Additional coverage for redis, models filters, routes, and app factory."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError

from fastapi_mongo_base.core import app_factory
from fastapi_mongo_base.core.config import ProjectSettings, Settings
from fastapi_mongo_base.db import redis as redis_db
from fastapi_mongo_base.errors.handlers import (
    general_exception_handler,
    request_validation_exception_handler,
)
from fastapi_mongo_base.errors.redis import RedisConnectionError
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.routes import AbstractBaseRouter, as_page
from fastapi_mongo_base.schemas import BaseEntitySchema
from fastapi_mongo_base.utils import basic


class _FilterEntitySchema(BaseEntitySchema):
    name: str = "x"
    score: int = 0


class _FilterEntity(_FilterEntitySchema, BaseEntity):
    class Settings(BaseEntity.Settings):
        name = "coverage_filter_entities"

    @classmethod
    def search_field_set(cls) -> list[str]:
        return ["name", "score", "created_at"]


class _ExcludedEntity(_FilterEntitySchema, BaseEntity):
    class Settings(BaseEntity.Settings):
        name = "coverage_excluded_entities"

    @classmethod
    def search_exclude_set(cls) -> list[str]:
        return ["name"]


def _http_request(method: str = "GET") -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": "/",
        "headers": [],
        "query_string": b"",
        "client": ("test", 50000),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    })


def test_build_extra_filters_variants() -> None:
    """Exercise Mongo extra filter builders for coverage."""
    range_filters = _FilterEntity._build_extra_filters(
        score_from=1,
        score_to=10,
        score=None,
        unknown_field=1,
    )
    assert range_filters["score"]["$gte"] == 1
    assert range_filters["score"]["$lte"] == 10
    assert "unknown_field" not in range_filters

    in_filters = _FilterEntity._build_extra_filters(
        name_in="a,b",
        name_nin=["z"],
    )
    assert in_filters["name"]["$nin"] == ["z"]

    like_filters = _FilterEntity._build_extra_filters(name_like="te")
    assert like_filters["name"]["$regex"] == "te"

    eq_filters = _FilterEntity._build_extra_filters(name="ok")
    assert eq_filters["name"] == "ok"

    excluded = _ExcludedEntity._build_extra_filters(name="blocked")
    assert "name" not in excluded

    restricted = _FilterEntity._build_extra_filters(meta_data="x")
    assert "meta_data" not in restricted


def test_adjust_pagination_with_query_defaults() -> None:
    """adjust_pagination accepts FastAPI Query defaults."""
    offset, limit = BaseEntity.adjust_pagination(Query(3), Query(None))
    assert offset == 3
    assert limit >= 1


def test_as_page_sets_total_from_items() -> None:
    """as_page fills total from item length when omitted."""
    page = as_page([{"a": 1}, {"a": 2}], offset=1, limit=5)
    assert page.total == 2
    assert page.offset == 1
    assert page.limit == 5


def test_app_factory_use_helpers() -> None:
    """URI presence helpers respect optional package availability."""
    settings = Settings()
    settings.mongo_uri = None
    settings.redis_uri = None
    settings.database_uri = None
    assert app_factory._use_mongodb(None) is False
    assert app_factory._use_redis(None) is False
    assert app_factory._use_sql(None) is False
    assert app_factory._use_mongodb(settings) is False
    assert app_factory._use_redis(settings) is False
    assert app_factory._use_sql(settings) is False

    settings.mongo_uri = "mongodb://localhost"
    settings.redis_uri = "redis://localhost"
    settings.database_uri = "sqlite+aiosqlite:///:memory:"
    assert app_factory._use_mongodb(settings) is True
    assert app_factory._use_redis(settings) is True
    assert app_factory._use_sql(settings) is True


def test_health_handler() -> None:
    """Liveness probe returns up."""
    request = MagicMock()
    assert app_factory.health(request)["status"] == "up"


@pytest.mark.asyncio
async def test_readiness_degraded_when_checks_fail() -> None:
    """Readiness returns 503 when dependency checks report down."""
    app = FastAPI()
    app.state.datasources = {"mongodb": True, "redis": True, "sql": True}
    app.state.mongo_client = None
    app.state.redis_async_client = None
    app.state.async_session = None
    request = MagicMock()
    request.app = app
    response = await app_factory.readiness(request)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_readiness_up_when_checks_pass() -> None:
    """Readiness is 200 when dependency checks report up."""
    app = FastAPI(version="1.2.3")
    app.state.datasources = {"mongodb": True}
    app.state.mongo_client = object()
    request = MagicMock()
    request.app = app
    with patch(
        "fastapi_mongo_base.core.app_factory.db.check_mongodb",
        new=AsyncMock(return_value="up"),
    ):
        response = await app_factory.readiness(request)
    assert response.status_code == 200


def test_redis_guard_proxies_and_force_exits() -> None:
    """Redis guards proxy attributes and force-exit on fatal errors."""
    client = MagicMock()
    client.get.return_value = "v"
    client.__getitem__.side_effect = lambda key: f"got-{key}"
    guard = redis_db._SyncRedisGuard(client)
    assert guard.get("k") == "v"
    assert guard["x"] == "got-x"
    guard["y"] = "z"
    client.__setitem__.assert_called()

    client.ping.side_effect = ConnectionError("down")
    with (
        patch.object(redis_db, "_force_exit") as force_exit,
        pytest.raises(ConnectionError),
    ):
        guard.ping()
    force_exit.assert_called_once()


@pytest.mark.asyncio
async def test_async_redis_guard_force_exit() -> None:
    """Async redis guard force-exits on fatal errors without killing pytest."""
    client = MagicMock()
    client.get = AsyncMock(return_value="v")
    client.ping = AsyncMock(return_value=True)
    guard = redis_db._AsyncRedisGuard(client)
    assert await guard.get("k") == "v"
    assert await guard.ping() is True
    guard["a"] = "b"
    assert guard["a"] == client["a"]

    client.ping = AsyncMock(side_effect=TimeoutError("t"))
    with (
        patch.object(redis_db, "_force_exit") as force_exit,
        pytest.raises(TimeoutError),
    ):
        await guard.ping()
    force_exit.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_close_redis() -> None:
    """check_redis and close_redis cover up/down and close paths."""
    assert await redis_db.check_redis(None) == "down"
    assert await redis_db.check_redis(object()) == "down"

    ok = MagicMock()
    ok.ping = AsyncMock(return_value=True)
    assert await redis_db.check_redis(ok) == "up"

    bad = MagicMock()
    bad.ping = AsyncMock(side_effect=RuntimeError("nope"))
    assert await redis_db.check_redis(bad) == "down"

    closing = MagicMock()
    closing.aclose = AsyncMock()
    closing.close = MagicMock()
    await redis_db.close_redis(sync_client=closing, async_client=closing)
    closing.aclose.assert_awaited()
    closing.close.assert_called()


def test_init_redis_paths() -> None:
    """init_redis covers unset URI, success, and RedisError failure."""

    @dataclasses.dataclass
    class _Settings:
        redis_uri: str | None = "redis://localhost:6379/0"

    assert redis_db.init_redis(_Settings(redis_uri=None)) == (None, None)

    redis_db._redis.async_client = None
    with pytest.raises(RedisConnectionError):
        redis_db.get_redis_async_client()

    mock_sync_cls = MagicMock()
    mock_async_cls = MagicMock()
    mock_sync = MagicMock()
    mock_async = MagicMock()
    mock_sync_cls.from_url.return_value = mock_sync
    mock_async_cls.from_url.return_value = mock_async
    mock_sync.ping.return_value = True

    with (
        patch("redis.Redis", mock_sync_cls),
        patch("redis.asyncio.client.Redis", mock_async_cls),
    ):
        sync_c, async_c = redis_db.init_redis(_Settings())
        assert isinstance(sync_c, redis_db._SyncRedisGuard)
        assert isinstance(async_c, redis_db._AsyncRedisGuard)
        assert redis_db.get_redis_async_client() is async_c
        assert redis_db.get_redis_sync_client() is sync_c

    from redis.exceptions import RedisError

    mock_sync.ping.side_effect = RedisError("boom")
    with (
        patch("redis.Redis", mock_sync_cls),
        patch("redis.asyncio.client.Redis", mock_async_cls),
        pytest.raises(RedisConnectionError),
    ):
        redis_db.init_redis(_Settings())


def test_basic_range_and_sync_retry() -> None:
    """Cover range validation and sync retry helper."""
    assert basic.is_valid_range_value(datetime.now(timezone.utc))
    assert basic.is_valid_range_value(Decimal("1"))

    calls = {"n": 0}

    @basic.retry_execution(attempts=3, delay=0)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("retry")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_basic_async_retry_and_debug_mock() -> None:
    """Async retry wrapper and debug_mode_mock callable path."""
    attempts = {"n": 0}

    @basic.retry_execution(attempts=2, delay=0)
    async def async_ok() -> str:
        await asyncio.sleep(0)
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ValueError("once")
        return "done"

    assert await async_ok() == "done"

    @basic.retry_execution(attempts=2, delay=0)
    async def always_fail() -> str:
        await asyncio.sleep(0)
        raise RuntimeError("always")

    with pytest.raises(RuntimeError):
        await always_fail()

    @basic.debug_mode_mock(lambda: "mocked")
    async def real() -> str:
        await asyncio.sleep(0)
        return "real"

    with patch.object(Settings, "debug", True):
        assert await real() == "mocked"


def test_router_requires_model() -> None:
    """AbstractBaseRouter validates model configuration."""

    class _BadRouter(AbstractBaseRouter):
        pass

    _BadRouter.model = None
    _BadRouter.schema = None
    with pytest.raises(ValueError, match="model is required"):
        _BadRouter()


@pytest.mark.asyncio
async def test_request_validation_handler_with_raw_body() -> None:
    """request_validation_exception_handler covers body preview branches."""
    request = _http_request("POST")
    request.state.raw_body = b"hello-body"
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "name"),
                "msg": "field required",
                "type": "missing",
            },
        ],
    )
    response = await request_validation_exception_handler(request, exc)
    assert response.status_code == 422


def test_general_exception_handler_fallback() -> None:
    """general_exception_handler returns internal error response."""
    response = general_exception_handler(
        _http_request(),
        RuntimeError("boom"),
    )
    assert response.status_code == 500


@pytest.mark.asyncio
@pytest.mark.usefixtures("db")
async def test_mongo_entity_crud_paths() -> None:
    """Cover create/get/list/update/delete on BaseEntity."""
    item = await _FilterEntity.create_item({"name": "alpha", "score": 5})
    assert item.name == "alpha"
    fetched = await _FilterEntity.get_item(item.uid)
    assert fetched is not None
    assert fetched.uid == item.uid

    listed = await _FilterEntity.list_items(limit=10, name_like="alp")
    assert any(x.uid == item.uid for x in listed)
    total = await _FilterEntity.total_count(name="alpha")
    assert total >= 1

    updated = await _FilterEntity.update_item(item, {"score": 9})
    assert updated.score == 9
    deleted = await _FilterEntity.delete_item(updated)
    assert deleted.is_deleted is True


def test_settings_config_logger_and_coverage_dir() -> None:
    """Settings helpers for logging and coverage directory."""
    Settings.config_logger()
    assert Settings.get_coverage_dir().name == "htmlcov"
    assert ProjectSettings.get_coverage_dir().name == "htmlcov"
