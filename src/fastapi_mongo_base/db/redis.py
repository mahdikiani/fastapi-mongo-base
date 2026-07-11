"""Redis connection initialization and health checks."""

from __future__ import annotations

import inspect
import logging

from ..core.config import Settings
from ..errors.redis import RedisConnectionError

_redis_sync_client: object | None = None
_redis_async_client: object | None = None


def get_redis_sync_client() -> object | None:
    """Return the initialized sync Redis client, if any."""
    return _redis_sync_client


def get_redis_async_client() -> object:
    """
    Return the initialized async Redis client.

    Raises:
        RedisConnectionError: When Redis is not configured or initialized.

    """
    if _redis_async_client is None:
        raise RedisConnectionError(
            "Redis async client is not initialized. "
            "Configure REDIS_URI and ensure init_redis() ran at startup."
        )
    return _redis_async_client


def init_redis(
    settings: Settings | None = None,
) -> tuple[object | None, object | None]:
    """
    Initialize Redis connections (sync and async).

    Args:
        settings: Optional settings instance. If None, creates a new instance.

    Returns:
        Tuple of (sync_redis_client, async_redis_client).
        Returns (None, None) when Redis is not configured.

    Raises:
        RedisConnectionError: If Redis is configured but connection fails.

    """
    global _redis_sync_client, _redis_async_client

    if settings is None:
        settings = Settings()

    redis_uri = getattr(settings, "redis_uri", None)
    if not redis_uri:
        _redis_sync_client = None
        _redis_async_client = None
        return None, None

    try:
        from redis import Redis as RedisSync
        from redis.asyncio.client import Redis
        from redis.exceptions import RedisError
    except ImportError as e:
        raise ImportError(
            "Redis is configured but redis package is not installed. "
            "Install with: pip install 'fastapi-mongo-base[redis]'"
        ) from e

    try:
        redis_sync: RedisSync = RedisSync.from_url(
            redis_uri,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        redis_async: Redis = Redis.from_url(
            redis_uri,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        redis_sync.ping()
    except RedisError as e:
        logging.exception("Redis connection error at %s", redis_uri)
        raise RedisConnectionError("Failed to connect to Redis") from e

    _redis_sync_client = redis_sync
    _redis_async_client = redis_async
    return redis_sync, redis_async


async def check_redis(client: object | None) -> str:
    """
    Ping Redis to verify readiness.

    Args:
        client: Async Redis client instance.

    Returns:
        "up" when reachable, otherwise "down".

    """
    if client is None:
        return "down"
    try:
        await client.ping()
    except Exception:
        logging.exception("Redis readiness check failed")
        return "down"
    else:
        return "up"


async def close_redis(
    sync_client: object | None = None,
    async_client: object | None = None,
) -> None:
    """
    Close Redis clients if supported.

    Args:
        sync_client: Optional sync Redis client override.
        async_client: Optional async Redis client override.

    """
    global _redis_sync_client, _redis_async_client

    sync_client = (
        sync_client if sync_client is not None else _redis_sync_client
    )
    async_client = (
        async_client if async_client is not None else _redis_async_client
    )

    if async_client is not None:
        for name in ("aclose", "close"):
            close = getattr(async_client, name, None)
            if close is None or not callable(close):
                continue
            if inspect.iscoroutinefunction(close):
                await close()
            else:
                close()
            break

    if sync_client is not None:
        close = getattr(sync_client, "close", None)
        if callable(close):
            close()

    _redis_sync_client = None
    _redis_async_client = None
