"""Backward compatibility shim. Prefer fastapi_mongo_base.db."""

from fastapi_mongo_base.db import (
    check_mongodb,
    check_redis,
    check_sql,
    close_mongo_client,
    close_redis,
    close_sql,
    create_sql_tables,
    discover_beanie_document_models,
    get_redis_async_client,
    get_redis_sync_client,
    get_sql_engine,
    get_sql_session_factory,
    init_mongo_db,
    init_redis,
    init_sql,
)

__all__ = [
    "check_mongodb",
    "check_redis",
    "check_sql",
    "close_mongo_client",
    "close_redis",
    "close_sql",
    "create_sql_tables",
    "discover_beanie_document_models",
    "get_redis_async_client",
    "get_redis_sync_client",
    "get_sql_engine",
    "get_sql_session_factory",
    "init_mongo_db",
    "init_redis",
    "init_sql",
]
