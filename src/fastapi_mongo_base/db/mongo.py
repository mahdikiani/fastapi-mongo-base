"""MongoDB connection initialization and health checks."""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from beanie import init_beanie

from fastapi_mongo_base.core.config import Settings
from fastapi_mongo_base.errors.mongodb import MongoDBConnectionError
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.utils import basic

logger = logging.getLogger(__name__)

_registered_pool_monitors: set[str] = set()


def discover_beanie_document_models() -> list[type]:
    """
    Discover concrete Beanie document models from BaseEntity subclasses.

    Abstract document classes (``Settings.__abstract__ = True``) are excluded.

    Returns:
        List of Beanie document model classes.

    """
    models: list[type] = []
    for cls in basic.get_all_subclasses(BaseEntity):
        settings_cls = cls.__dict__.get("Settings")
        if settings_cls is not None and getattr(
            settings_cls, "__abstract__", False
        ):
            continue
        models.append(cls)
    return models


def _register_pool_monitor(settings: Settings) -> None:
    """Register a MongoDB pool monitor once per project name."""
    if settings.project_name in _registered_pool_monitors:
        return
    try:
        from pymongo import monitoring

        from fastapi_mongo_base.monitoring.mongo import DatabasePoolMonitor

        pool_monitor = DatabasePoolMonitor(
            database_name=settings.project_name,
        )
        monitoring.register(pool_monitor)
        _registered_pool_monitors.add(settings.project_name)
    except ImportError:
        pass


async def init_mongo_db(
    settings: Settings | None = None,
    document_models: list[type] | None = None,
) -> tuple[object, object]:
    """
    Initialize MongoDB connection and Beanie ODM.

    The MongoDB **database name** is taken from ``settings.project_name``.
    Fails fast on connection errors so the application does not start degraded.

    Args:
        settings: Optional settings instance. If None, creates a new instance.
        document_models: Optional explicit Beanie document model list. When
            omitted, models are auto-discovered from ``BaseEntity`` subclasses.

    Returns:
        Tuple of (MongoDB database instance, MongoDB client instance).

    Raises:
        ImportError: If MongoDB client libraries are not installed.
        MongoDBConnectionError: If MongoDB connection or initialization fails.

    """
    client_cls: type[Any]
    try:
        from pymongo import AsyncMongoClient
        from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

        client_cls = AsyncMongoClient
    except ImportError:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            from pymongo.errors import (
                PyMongoError,
                ServerSelectionTimeoutError,
            )

            client_cls = AsyncIOMotorClient
        except ImportError as e:
            raise ImportError("MongoDB is not installed") from e

    resolved: Settings = (
        settings if settings is not None else cast("Settings", Settings())
    )

    mongo_uri = getattr(resolved, "mongo_uri", None)
    if not mongo_uri or not str(mongo_uri).strip():
        raise MongoDBConnectionError(
            "MongoDB is not configured. Set MONGO_URI to initialize."
        )

    _register_pool_monitor(resolved)

    client = client_cls(
        resolved.mongo_uri,
        serverSelectionTimeoutMS=resolved.mongo_server_selection_timeout_ms,
        connectTimeoutMS=resolved.mongo_connect_timeout_ms,
    )
    models = document_models or discover_beanie_document_models()
    if getattr(resolved, "audit_log_enabled", False):
        from fastapi_mongo_base.audit.context import set_audit_enabled
        from fastapi_mongo_base.audit.models import (
            AuditLog,
            activate_mongo_audit_log,
        )

        activate_mongo_audit_log()
        set_audit_enabled(True)
        if AuditLog not in models:
            models = [*models, AuditLog]
    else:
        from fastapi_mongo_base.audit.context import set_audit_enabled
        from fastapi_mongo_base.audit.models import deactivate_mongo_audit_log

        deactivate_mongo_audit_log()
        set_audit_enabled(False)

    try:
        await client.server_info()
        db = client.get_database(resolved.project_name)
        await init_beanie(
            database=cast("Any", db),
            document_models=cast("list[type[Any]]", models),
        )
    except ServerSelectionTimeoutError as e:
        logger.exception(
            "MongoDB connection timeout at %s", resolved.mongo_uri
        )
        raise MongoDBConnectionError("Failed to connect to MongoDB") from e

    except PyMongoError as e:
        logger.exception("MongoDB error at %s", resolved.mongo_uri)
        raise MongoDBConnectionError("Failed to connect to MongoDB") from e

    except Exception as e:
        logger.exception("Unexpected failure initializing MongoDB")
        raise MongoDBConnectionError("Failed to connect to MongoDB") from e

    return db, client


async def check_mongodb(client: object | None) -> str:
    """
    Ping MongoDB to verify readiness.

    Args:
        client: Async MongoDB client instance.

    Returns:
        "up" when reachable, otherwise "down".

    """
    if client is None:
        return "down"
    try:
        admin = getattr(client, "admin", None)
        if admin is None:
            return "down"
        await admin.command("ping")
    except Exception:
        logger.exception("MongoDB readiness check failed")
        return "down"
    else:
        return "up"


async def close_mongo_client(client: object | None) -> None:
    """
    Close an async MongoDB client if supported.

    Args:
        client: Async MongoDB client instance.

    """
    if client is None:
        return
    for name in ("aclose", "close"):
        close = getattr(client, name, None)
        if close is None or not callable(close):
            continue
        if inspect.iscoroutinefunction(close):
            await close()
        else:
            close()
        return
