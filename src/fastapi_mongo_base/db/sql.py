"""SQLAlchemy connection initialization and health checks."""

from __future__ import annotations

import logging

from ..core.config import Settings
from ..errors.sql import SQLConnectionError

_sql_engine: object | None = None
_sql_session_factory: object | None = None


def get_sql_session_factory() -> object | None:
    """Return the initialized async SQLAlchemy session factory, if any."""
    return _sql_session_factory


def get_sql_engine() -> object | None:
    """Return the initialized async SQLAlchemy engine, if any."""
    return _sql_engine


def _build_engine_kwargs(settings: Settings) -> dict[str, object]:
    """Build optional SQLAlchemy engine kwargs from settings."""
    kwargs: dict[str, object] = {
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
        from ..sql.models import BaseEntity

        metadata = BaseEntity.metadata

    if include_audit_log:
        from ..audit.sql import activate_sql_audit_log

        activate_sql_audit_log()

    def _create_all(connection: object) -> None:
        if include_audit_log:
            metadata.create_all(connection)
            return
        tables = [
            table
            for table in metadata.sorted_tables
            if table.name != "audit_logs"
        ]
        metadata.create_all(connection, tables=tables)

    async with engine.begin() as connection:
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
    global _sql_engine, _sql_session_factory

    if settings is None:
        settings = Settings()

    database_uri = getattr(settings, "database_uri", None)
    if not database_uri:
        _sql_engine = None
        _sql_session_factory = None
        return None, None

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )
    except ImportError as e:
        raise ImportError(
            "SQL is configured but SQLAlchemy is not installed. "
            "Install with: pip install 'fastapi-mongo-base[sql]'"
        ) from e

    audit_enabled = bool(getattr(settings, "audit_log_enabled", False))
    from ..audit.context import set_audit_enabled
    from ..audit.sql import activate_sql_audit_log, deactivate_sql_audit_log

    if audit_enabled:
        activate_sql_audit_log()
    else:
        deactivate_sql_audit_log()
    set_audit_enabled(audit_enabled)

    try:
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
        if create_tables:
            await create_sql_tables(
                engine,
                metadata=metadata,
                include_audit_log=audit_enabled,
            )
    except Exception as e:
        logging.exception("SQL connection error at %s", database_uri)
        raise SQLConnectionError("Failed to connect to SQL database") from e

    from ..sql import models as sql_models
    from ..sql import session as sql_session_module

    sql_session_module.async_session = session_factory
    sql_models.async_session = session_factory
    _sql_engine = engine
    _sql_session_factory = session_factory
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

        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logging.exception("SQL readiness check failed")
        return "down"
    else:
        return "up"


async def close_sql(engine: object | None = None) -> None:
    """
    Dispose the SQLAlchemy engine and clear the session hook.

    Args:
        engine: Optional engine override.

    """
    global _sql_engine, _sql_session_factory

    engine = engine if engine is not None else _sql_engine
    if engine is not None:
        dispose = getattr(engine, "dispose", None)
        if callable(dispose):
            result = dispose()
            if hasattr(result, "__await__"):
                await result

    from ..sql import models as sql_models
    from ..sql import session as sql_session_module

    sql_session_module.async_session = None
    sql_models.async_session = None
    _sql_engine = None
    _sql_session_factory = None
