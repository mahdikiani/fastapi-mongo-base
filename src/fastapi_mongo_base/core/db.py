"""Database initialization for MongoDB and Redis."""

import logging

from beanie import init_beanie

from fastapi_mongo_base.core.errors.db_errors import from_pymongo_error
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.utils import basic

from .config import Settings


async def init_mongo_db(settings: Settings | None = None) -> object:
    """
    Initialize MongoDB connection and Beanie ODM.

    Fails fast on connection errors (unreachable host, timeout, etc.) so the
    application does not start in a degraded state.

    Args:
        settings: Optional settings instance. If None, creates a new instance.

    Returns:
        MongoDB database instance.

    Raises:
        ImportError: If MongoDB client libraries are not installed.
        SystemExit: If connection fails and ``exit_on_init_failure`` is
            enabled (default; use in Docker so the container restarts
            until Mongo is up).
        MongoDBConnectionError: If MongoDB connection or initialization fails
            and ``exit_on_init_failure`` is disabled.
        MongoDBConnectionTimeoutError: If MongoDB connection times out and
            ``exit_on_init_failure`` is disabled.

    """
    try:
        from pymongo import AsyncMongoClient
    except ImportError:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            AsyncMongoClient = AsyncIOMotorClient  # noqa: N806
        except ImportError as e:
            raise ImportError("MongoDB is not installed") from e

    if settings is None:
        settings = Settings()

    try:
        client = AsyncMongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
            connectTimeoutMS=settings.mongo_connect_timeout_ms,
        )
        await client.server_info()
        db = client.get_database(settings.project_name)
        await init_beanie(
            database=db,
            document_models=[
                cls
                for cls in basic.get_all_subclasses(BaseEntity)
                if not (
                    "Settings" in cls.__dict__
                    and getattr(cls.Settings, "__abstract__", False)
                )
            ],
        )
    except Exception as e:
        logging.exception(
            "MongoDB initialization failed at %s", settings.mongo_uri
        )
        raise from_pymongo_error(e, settings=settings) from e

    return db


def init_redis(settings: Settings | None = None) -> tuple:
    """
    Initialize Redis connections (sync and async).

    Args:
        settings: Optional settings instance. If None, creates a new instance.

    Returns:
        Tuple of (sync_redis_client, async_redis_client).
        Returns (None, None) if Redis is not configured or unavailable.

    """
    if settings is None:
        settings = Settings()

    try:
        from redis import Redis as RedisSync
        from redis.asyncio.client import Redis
        from redis.exceptions import RedisError

        redis_uri = getattr(settings, "redis_uri", None)
        if redis_uri:
            redis_sync: RedisSync = RedisSync.from_url(
                redis_uri,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            redis: Redis = Redis.from_url(
                redis_uri,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            redis_sync.ping()

            return redis_sync, redis
    except RedisError as e:
        logging.exception("Redis connection error")
        if settings.exit_on_init_failure:
            raise SystemExit(1) from e
    except (ImportError, AttributeError, Exception):
        logging.exception("Error initializing Redis")

    return None, None
