"""MongoDB connection initialization and health checks."""

from __future__ import annotations

import inspect
import logging

from beanie import init_beanie

from ..core.config import Settings
from ..errors.mongodb import MongoDBConnectionError
from ..models import BaseEntity
from ..utils import basic

_registered_pool_monitors: set[str] = set()


def discover_beanie_document_models() -> list[type]:
    """
    Discover concrete Beanie document models from BaseEntity subclasses.

    Abstract document classes (``Settings.__abstract__ = True``) are excluded.

    Returns:
        List of Beanie document model classes.

    """
    return [
        cls
        for cls in basic.get_all_subclasses(BaseEntity)
        if not (
            "Settings" in cls.__dict__
            and getattr(cls.Settings, "__abstract__", False)
        )
    ]


def _register_pool_monitor(settings: Settings) -> None:
    """Register a MongoDB pool monitor once per project name."""
    if settings.project_name in _registered_pool_monitors:
        return
    try:
        from pymongo import monitoring

        from ..monitoring.mongo import DatabasePoolMonitor

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
    try:
        from pymongo import AsyncMongoClient
        from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
    except ImportError:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            AsyncMongoClient = AsyncIOMotorClient  # ruff:ignore[non-lowercase-variable-in-function]
        except ImportError as e:
            raise ImportError("MongoDB is not installed") from e

    if settings is None:
        settings = Settings()

    mongo_uri = getattr(settings, "mongo_uri", None)
    if not mongo_uri or not str(mongo_uri).strip():
        raise MongoDBConnectionError(
            "MongoDB is not configured. Set MONGO_URI to initialize."
        )

    _register_pool_monitor(settings)

    client = AsyncMongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
        connectTimeoutMS=settings.mongo_connect_timeout_ms,
    )
    models = document_models or discover_beanie_document_models()
    if getattr(settings, "audit_log_enabled", False):
        from ..audit.context import set_audit_enabled
        from ..audit.models import AuditLog, activate_mongo_audit_log

        activate_mongo_audit_log()
        set_audit_enabled(True)
        if AuditLog not in models:
            models = [*models, AuditLog]
    else:
        from ..audit.context import set_audit_enabled
        from ..audit.models import deactivate_mongo_audit_log

        deactivate_mongo_audit_log()
        set_audit_enabled(False)

    try:
        await client.server_info()
        db = client.get_database(settings.project_name)
        await init_beanie(database=db, document_models=models)
    except ServerSelectionTimeoutError as e:
        logging.exception(
            "MongoDB connection timeout at %s", settings.mongo_uri
        )
        raise MongoDBConnectionError("Failed to connect to MongoDB") from e

    except PyMongoError as e:
        logging.exception("MongoDB error at %s", settings.mongo_uri)
        raise MongoDBConnectionError("Failed to connect to MongoDB") from e

    except Exception as e:
        logging.exception("Unexpected failure initializing MongoDB")
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
        logging.exception("MongoDB readiness check failed")
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
