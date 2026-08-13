"""SQLAlchemy connection initialization and health checks."""

from __future__ import annotations

import importlib.util
import logging
from typing import Any, cast

from fastapi_mongo_base.core.config import Settings
from fastapi_mongo_base.errors.sql import SQLConnectionError

logger = logging.getLogger(__name__)


class _SqlRuntime:
    """Mutable SQL engine/session handles (avoids ``global``)."""

    engine: object | None = None
    session_factory: object | None = None


_sql = _SqlRuntime()


def get_sql_session_factory() -> object | None:
    """Return the initialized async SQLAlchemy session factory, if any."""
    return _sql.session_factory


def get_sql_engine() -> object | None:
    """Return the initialized async SQLAlchemy engine, if any."""
    return _sql.engine


def _build_engine_kwargs(settings: Settings) -> dict[str, Any]:
    """Build optional SQLAlchemy engine kwargs from settings."""
    kwargs: dict[str, Any] = {
        "echo": getattr(settings, "database_echo", False),
    }

    if getattr(settings, "database_pool_pre_ping", True):
        kwargs["pool_pre_ping"] = True

    for setting_name, engine_key in (
        ("database_pool_size", "pool_size"),
        ("database_max_overflow", "max_overflow"),
        ("database_pool_timeout", "pool_timeout"),
        ("database_pool_recycle", "pool_recycle"),
    ):
        value = getattr(settings, setting_name, None)
        if value is not None:
            kwargs[engine_key] = value

    return kwargs


async def _connect_sql(
    database_uri: str,
    settings: Settings,
) -> tuple[Any, Any]:
    """Create the async engine, session factory, and verify connectivity."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(
        database_uri,
        **_build_engine_kwargs(settings),
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return engine, session_factory


async def create_sql_tables(
    engine: object,
    metadata: object | None = None,
    *,
    include_audit_log: bool = False,
) -> None:
    """
    Create SQL tables for the provided metadata.

    Args:
        engine: Async SQLAlchemy engine instance.
        metadata: Optional metadata object. Defaults to ``BaseEntity``
            ``.metadata``.
        include_audit_log: Whether to create the audit_logs table.

    """
    if metadata is None:
        from fastapi_mongo_base.sql.models import BaseEntity

        metadata = cast("Any", BaseEntity).metadata

    meta = cast("Any", metadata)
    engine_any = cast("Any", engine)

    if include_audit_log:
        from fastapi_mongo_base.audit.sql import activate_sql_audit_log

        activate_sql_audit_log()

    def _create_all(connection: object) -> None:
        if include_audit_log:
            meta.create_all(connection)
            return
        tables = [
            table for table in meta.sorted_tables if table.name != "audit_logs"
        ]
        meta.create_all(connection, tables=tables)

    async with engine_any.begin() as connection:
        await connection.run_sync(_create_all)


async def init_sql(
    settings: Settings | None = None,
    *,
    create_tables: bool = False,
    metadata: object | None = None,
) -> tuple[object | None, object | None]:
    """
    Initialize the SQLAlchemy async engine and session factory.

    When configured, assigns ``fastapi_mongo_base.sql.session.async_session``
    so base SQL models can run queries.

    Args:
        settings: Optional settings instance. If None, creates a new instance.
        create_tables: Whether to run ``metadata.create_all`` after connecting.
        metadata: Optional metadata for ``create_tables``.

    Returns:
        Tuple of (async engine, async session factory), or (None, None).

    Raises:
        SQLConnectionError: If SQL is configured but connection fails.

    """
    resolved: Settings = (
        settings if settings is not None else cast("Settings", Settings())
    )

    database_uri = getattr(resolved, "database_uri", None)
    if not database_uri:
        _sql.engine = None
        _sql.session_factory = None
        return None, None

    if importlib.util.find_spec("sqlalchemy") is None:
        raise ImportError(
            "SQL is configured but SQLAlchemy is not installed. "
            "Install with: pip install 'fastapi-mongo-base[sql]'"
        )

    audit_enabled = bool(getattr(resolved, "audit_log_enabled", False))
    from fastapi_mongo_base.audit.context import set_audit_enabled
    from fastapi_mongo_base.audit.sql import (
        activate_sql_audit_log,
        deactivate_sql_audit_log,
    )

    if audit_enabled:
        activate_sql_audit_log()
    else:
        deactivate_sql_audit_log()
    set_audit_enabled(audit_enabled)

    try:
        engine, session_factory = await _connect_sql(database_uri, resolved)
        if create_tables:
            await create_sql_tables(
                engine,
                metadata=metadata,
                include_audit_log=audit_enabled,
            )
    except ImportError:
        raise
    except Exception as e:
        logger.exception("SQL connection error at %s", database_uri)
        raise SQLConnectionError("Failed to connect to SQL database") from e

    from fastapi_mongo_base.sql import models as sql_models
    from fastapi_mongo_base.sql import session as sql_session_module

    sql_session_module.async_session = session_factory
    sql_models.async_session = session_factory
    _sql.engine = engine
    _sql.session_factory = session_factory
    return engine, session_factory


async def check_sql(session_factory: object | None) -> str:
    """
    Ping the SQL database to verify readiness.

    Args:
        session_factory: Async SQLAlchemy session factory.

    Returns:
        "up" when reachable, otherwise "down".

    """
    if session_factory is None:
        return "down"
    try:
        from sqlalchemy import text

        async with cast("Any", session_factory)() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("SQL readiness check failed")
        return "down"
    else:
        return "up"


async def close_sql(engine: object | None = None) -> None:
    """
    Dispose the SQLAlchemy engine and clear the session hook.

    Args:
        engine: Optional engine override.

    """
    engine = engine if engine is not None else _sql.engine
    if engine is not None:
        dispose = getattr(engine, "dispose", None)
        if callable(dispose):
            result = dispose()
            if hasattr(result, "__await__"):
                await result

    from fastapi_mongo_base.sql import models as sql_models
    from fastapi_mongo_base.sql import session as sql_session_module

    sql_session_module.async_session = None
    sql_models.async_session = None
    _sql.engine = None
    _sql.session_factory = None
