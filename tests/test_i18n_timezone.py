"""Tests for request timezone helpers and response serialization."""

from __future__ import annotations

from datetime import datetime

import pytest
import pytz
from fastapi import FastAPI, Request
from starlette.testclient import TestClient

from src.fastapi_mongo_base.i18n.context import request_timezone
from src.fastapi_mongo_base.i18n.timezone import (
    apply_user_timezone,
    localize_filter_datetime,
    parse_timezone,
    resolve_request_timezone,
    serialize_response_datetime,
    set_request_timezone,
)
from src.fastapi_mongo_base.middlewares.timezone import TimezoneMiddleware
from src.fastapi_mongo_base.schemas import BaseEntitySchema
from src.fastapi_mongo_base.tasks import TaskLogRecord, TaskMixin
from src.fastapi_mongo_base.utils import timezone as tz_util


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({
        "type": "http",
        "headers": headers or [],
        "method": "GET",
        "path": "/",
    })


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Asia/Tehran", "Asia/Tehran"),
        (" UTC ", "UTC"),
        (None, None),
        ("", None),
        ("Not/AZone", None),
    ],
)
def test_parse_timezone(value: str | None, expected: str | None) -> None:
    """parse_timezone accepts IANA names and rejects invalid values."""
    parsed = parse_timezone(value)
    if expected is None:
        assert parsed is None
    else:
        assert parsed is not None
        assert str(parsed) == expected


def test_resolve_request_timezone_prefers_user_then_header() -> None:
    """Timezone resolution follows user > header > app default."""
    request = _request([(b"x-timezone", b"Europe/Berlin")])

    resolved = resolve_request_timezone(
        request,
        user_timezone="Asia/Tehran",
    )
    assert str(resolved) == "Asia/Tehran"

    header_only = resolve_request_timezone(request)
    assert str(header_only) == "Europe/Berlin"

    fallback = resolve_request_timezone(_request())
    assert fallback == tz_util.tz


def test_apply_user_timezone_overrides_request_state() -> None:
    """Authenticated user timezone overrides header-based resolution."""

    class _User:
        timezone = "Asia/Tehran"

    request = _request([(b"x-timezone", b"Europe/Berlin")])
    set_request_timezone(request, pytz.timezone("UTC"))
    apply_user_timezone(request, _User())

    assert str(request.state.timezone) == "Asia/Tehran"
    assert str(request_timezone.get()) == "Asia/Tehran"


def test_serialize_response_datetime_uses_context() -> None:
    """Datetime serialization converts UTC storage to request timezone."""
    token = request_timezone.set(pytz.timezone("Asia/Tehran"))
    try:
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=pytz.UTC)
        result = serialize_response_datetime(dt)
        assert result == "2024-06-01T15:30:00+03:30"
    finally:
        request_timezone.reset(token)


def test_serialize_response_datetime_treats_naive_as_utc() -> None:
    """Naive datetimes are interpreted as UTC before conversion."""
    token = request_timezone.set(pytz.UTC)
    try:
        dt = datetime(2024, 6, 1, 12, 0, 0)
        assert serialize_response_datetime(dt) == "2024-06-01T12:00:00Z"
    finally:
        request_timezone.reset(token)


def test_localize_filter_datetime_converts_to_utc() -> None:
    """Filter datetimes are converted from request timezone to UTC."""
    token = request_timezone.set(pytz.timezone("Asia/Tehran"))
    try:
        local = datetime(2024, 6, 1, 15, 30, 0)
        utc_dt = localize_filter_datetime(local)
        assert utc_dt == datetime(2024, 6, 1, 12, 0, 0, tzinfo=pytz.UTC)
    finally:
        request_timezone.reset(token)


def test_base_entity_schema_serializes_created_at_in_request_timezone() -> (
    None
):
    """BaseEntitySchema JSON output uses request timezone."""
    token = request_timezone.set(pytz.timezone("Asia/Tehran"))
    try:
        schema = BaseEntitySchema(
            uid="item-1",
            created_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=pytz.UTC),
            updated_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=pytz.UTC),
        )
        payload = schema.model_dump(mode="json")
        assert payload["created_at"] == "2024-06-01T15:30:00+03:30"
        assert payload["updated_at"] == "2024-06-01T15:30:00+03:30"
    finally:
        request_timezone.reset(token)


class _TaskEntity(TaskMixin):
    """Minimal task entity for serializer tests."""


def test_task_mixin_serializes_task_datetimes() -> None:
    """TaskMixin exposes timezone-aware task timestamps in JSON."""
    token = request_timezone.set(pytz.UTC)
    try:
        task = _TaskEntity(
            task_start_at=datetime(2024, 6, 1, 8, 0, 0, tzinfo=pytz.UTC),
            task_end_at=None,
        )
        payload = task.model_dump(mode="json")
        assert payload["task_start_at"] == "2024-06-01T08:00:00Z"
        assert payload["task_end_at"] is None
    finally:
        request_timezone.reset(token)


def test_task_log_record_serializes_reported_at() -> None:
    """Task log records serialize reported_at in request timezone."""
    token = request_timezone.set(pytz.UTC)
    try:
        record = TaskLogRecord(
            reported_at=datetime(2024, 6, 1, 8, 0, 0, tzinfo=pytz.UTC),
            message="done",
            task_status="done",
        )
        payload = record.model_dump(mode="json")
        assert payload["reported_at"] == "2024-06-01T08:00:00Z"
    finally:
        request_timezone.reset(token)


def test_timezone_middleware_binds_request_timezone() -> None:
    """Middleware resolves timezone from X-Timezone header."""
    app = FastAPI()
    app.add_middleware(TimezoneMiddleware)

    @app.get("/tz")
    def read_timezone(request: Request) -> dict[str, str]:
        return {"timezone": str(request.state.timezone)}

    client = TestClient(app)
    response = client.get("/tz", headers={"X-Timezone": "Asia/Tehran"})

    assert response.status_code == 200
    assert response.json()["timezone"] == "Asia/Tehran"
