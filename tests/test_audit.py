"""Tests for audit log schema, emission, and DB registration."""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from src.fastapi_mongo_base.audit.context import (
    AuditActor,
    bind_audit_actor,
    is_audit_enabled,
    reset_audit_actor,
    set_audit_enabled,
)
from src.fastapi_mongo_base.audit.diff import compute_changes
from src.fastapi_mongo_base.audit.models import (
    AuditLog,
    activate_mongo_audit_log,
    deactivate_mongo_audit_log,
)
from src.fastapi_mongo_base.audit.schemas import AuditAction
from src.fastapi_mongo_base.db.mongo import (
    discover_beanie_document_models,
    init_mongo_db,
)
from src.fastapi_mongo_base.models import TenantScopedEntity
from src.fastapi_mongo_base.schemas import TenantScopedEntitySchema

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from sqlalchemy.orm import Mapped, mapped_column

from src.fastapi_mongo_base.sql.models import (
    BaseEntity as SqlBaseEntity,
)
from src.fastapi_mongo_base.sql.models import (
    TenantScopedEntity as SqlTenantScopedEntity,
)


class _WidgetSchema(TenantScopedEntitySchema):
    name: str
    value: int = 0


class _Widget(_WidgetSchema, TenantScopedEntity):
    class Settings(TenantScopedEntity.Settings):
        name = "audit_test_widgets"
        __abstract__ = False


class _SqlWidget(SqlTenantScopedEntity):
    __tablename__ = "audit_sql_widgets"

    name: Mapped[str] = mapped_column(default="")


@pytest.fixture(autouse=True)
def _reset_audit_flag() -> None:
    set_audit_enabled(False)
    deactivate_mongo_audit_log()
    yield
    set_audit_enabled(False)
    deactivate_mongo_audit_log()


def test_audit_log_excluded_from_discovery_by_default() -> None:
    """AuditLog stays abstract and is not auto-discovered."""
    assert AuditLog.Settings.__abstract__ is True
    assert AuditLog not in discover_beanie_document_models()


def test_compute_changes_reports_field_diff() -> None:
    """compute_changes returns sparse old/new pairs."""
    changes = compute_changes(
        {"name": "a", "value": 1},
        {"name": "b", "value": 1},
    )
    assert changes == {"name": {"old": "a", "new": "b"}}


@pytest.mark.asyncio
async def test_init_mongo_registers_audit_log_when_enabled() -> None:
    """Enabled setting should activate and pass AuditLog to init_beanie."""

    @dataclasses.dataclass
    class _Settings:
        mongo_uri: str = "mongodb://localhost:27017"
        project_name: str = "audit_test"
        mongo_server_selection_timeout_ms: int = 1000
        mongo_connect_timeout_ms: int = 1000
        audit_log_enabled: bool = True

    mock_client = MagicMock()
    mock_client.server_info = AsyncMock(return_value={"ok": 1})
    mock_client.get_database.return_value = MagicMock()
    captured: dict[str, object] = {}

    async def _fake_init_beanie(  # ruff:ignore[unused-async]
        **kwargs: object,
    ) -> None:
        captured["models"] = kwargs["document_models"]

    with (
        patch("pymongo.AsyncMongoClient", return_value=mock_client),
        patch(
            "src.fastapi_mongo_base.db.mongo.init_beanie",
            side_effect=_fake_init_beanie,
        ),
    ):
        await init_mongo_db(_Settings())

    assert is_audit_enabled() is True
    assert AuditLog in captured["models"]  # type: ignore[operator]
    assert AuditLog.Settings.__abstract__ is False


@pytest_asyncio.fixture
async def widget_db() -> AsyncGenerator[None]:
    """Initialize mongomock with widget + audit log models."""
    set_audit_enabled(True)
    activate_mongo_audit_log()
    client = AsyncMongoMockClient()
    database = client.get_database("audit_widgets")
    orig = database.delegate.list_collection_names

    def _patched_list_collection_names(
        filter: dict | None = None,  # ruff:ignore[builtin-argument-shadowing]
        session: object | None = None,
        **kwargs: object,
    ) -> list[str]:
        return orig(filter=filter, session=session)

    database.delegate.list_collection_names = _patched_list_collection_names
    await init_beanie(
        database=database,
        document_models=[_Widget, AuditLog],
    )
    yield
    deactivate_mongo_audit_log()
    set_audit_enabled(False)


@pytest.mark.asyncio
async def test_create_update_delete_emit_audit_rows(
    widget_db: None,
) -> None:
    """CRUD hooks should persist create/update/delete audit rows."""
    token = bind_audit_actor(
        AuditActor(
            tenant_id="t1",
            user_id="u1",
            sub_type="user",
            principal_id="u1",
        ),
    )
    try:
        widget = await _Widget.create_item({
            "tenant_id": "t1",
            "name": "alpha",
            "value": 1,
        })
        await _Widget.update_item(widget, {"name": "beta"})
        await _Widget.delete_item(widget)
    finally:
        reset_audit_actor(token)

    rows = await AuditLog.find_all().to_list()
    actions = [
        row.action.value if hasattr(row.action, "value") else row.action
        for row in rows
    ]
    assert actions == [
        AuditAction.create.value,
        AuditAction.update.value,
        AuditAction.delete.value,
    ]

    create_row = rows[0]
    assert create_row.actor_user_id == "u1"
    assert create_row.resource_type == "_Widget"
    assert create_row.resource_uid == widget.uid
    assert create_row.snapshot_after is not None
    assert create_row.changes is not None

    update_row = rows[1]
    assert update_row.changes is not None
    assert update_row.changes["name"]["old"] == "alpha"
    assert update_row.changes["name"]["new"] == "beta"

    delete_row = rows[2]
    assert delete_row.action in (AuditAction.delete, AuditAction.delete.value)
    assert delete_row.snapshot_before is not None
    assert delete_row.changes is not None
    assert delete_row.changes.get("is_deleted", {}).get("new") is True


@pytest.mark.asyncio
async def test_no_audit_when_disabled(widget_db: None) -> None:
    """When flag is off, mutations must not write audit rows."""
    set_audit_enabled(False)
    await _Widget.create_item({
        "tenant_id": "t1",
        "name": "gamma",
        "value": 3,
    })
    assert await AuditLog.find_all().count() == 0


@pytest.mark.asyncio
async def test_sql_audit_table_created_only_when_enabled() -> None:
    """SQL create_tables should include audit_logs only when enabled."""
    from sqlalchemy import inspect

    from src.fastapi_mongo_base.audit.sql import deactivate_sql_audit_log
    from src.fastapi_mongo_base.core.db import close_sql, init_sql

    @dataclasses.dataclass
    class _SqlSettings:
        database_uri: str = "sqlite+aiosqlite:///:memory:"
        audit_log_enabled: bool = False

    deactivate_sql_audit_log()
    engine, _ = await init_sql(
        _SqlSettings(audit_log_enabled=False),
        create_tables=True,
        metadata=SqlBaseEntity.metadata,
    )
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names(),
            )
        assert "audit_logs" not in tables
    finally:
        await close_sql(engine)

    deactivate_sql_audit_log()
    engine, _ = await init_sql(
        _SqlSettings(audit_log_enabled=True),
        create_tables=True,
        metadata=SqlBaseEntity.metadata,
    )
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names(),
            )
        assert "audit_logs" in tables
        assert is_audit_enabled() is True
    finally:
        await close_sql(engine)
        deactivate_sql_audit_log()
        set_audit_enabled(False)


@pytest.mark.asyncio
async def test_sql_crud_emits_delete_action() -> None:
    """SQL twin should record distinguishable delete audits."""
    from src.fastapi_mongo_base.audit.sql import (
        activate_sql_audit_log,
        deactivate_sql_audit_log,
        get_sql_audit_log_model,
    )
    from src.fastapi_mongo_base.core.db import close_sql, init_sql

    @dataclasses.dataclass
    class _SqlSettings:
        database_uri: str = "sqlite+aiosqlite:///:memory:"
        audit_log_enabled: bool = True

    deactivate_sql_audit_log()
    engine, session_factory = await init_sql(
        _SqlSettings(),
        create_tables=True,
        metadata=SqlBaseEntity.metadata,
    )
    try:
        set_audit_enabled(True)
        activate_sql_audit_log()
        with patch(
            "src.fastapi_mongo_base.sql.models.async_session",
            session_factory,
        ):
            token = bind_audit_actor(
                AuditActor(
                    tenant_id="t1",
                    user_id="u9",
                    sub_type="user",
                    principal_id="u9",
                ),
            )
            try:
                item = await _SqlWidget.create_item({
                    "tenant_id": "t1",
                    "name": "one",
                })
                await _SqlWidget.delete_item(item)
            finally:
                reset_audit_actor(token)

            audit_model = get_sql_audit_log_model()
            assert audit_model is not None
            rows = await audit_model.list_items(tenant_id="t1", limit=50)
            assert len(rows) >= 2
            actions = {row.action for row in rows}
            assert "create" in actions
            assert "delete" in actions
            delete_rows = [row for row in rows if row.action == "delete"]
            assert delete_rows[0].actor_user_id == "u9"
    finally:
        await close_sql(engine)
        deactivate_sql_audit_log()
        set_audit_enabled(False)
