"""Redis connection initialization and health checks."""

from __future__ import annotations

import inspect
import logging
import os

from ..core.config import Settings
from ..errors.redis import RedisConnectionError

_redis_sync_client: object | None = None
_redis_async_client: object | None = None
logger = logging.getLogger(__name__)


def _redis_fatal_exceptions() -> tuple[type[BaseException], ...]:
    """Connection-related and script errors that should kill the process."""
    try:
        from redis.exceptions import NoScriptError
    except ImportError:  # redis not installed; nothing to guard against
        return ()
    return (ConnectionError, NoScriptError, TimeoutError, OSError)


def _force_exit(exc: BaseException, method_name: str) -> None:
    """Log and forcefully terminate the process."""
    logger.critical(
        "Fatal Redis error on %s; forcing process exit",
        method_name,
        exc_info=exc,
    )
    os._exit(1)


class _SyncRedisGuard:
    """Proxy that force-exits on fatal Redis errors for sync calls."""

    def __init__(self, client: object) -> None:
        self._client = client
        self._fatal = _redis_fatal_exceptions()

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        def guarded(*args: object, **kwargs: object) -> object:
            try:
                return attr(*args, **kwargs)
            except self._fatal as e:
                _force_exit(e, name)
                raise  # pragma: no cover - unreachable after os._exit

        return guarded

    def __getitem__(self, key: object) -> object:
        return self._client[key]

    def __setitem__(self, key: object, value: object) -> None:
        self._client[key] = value


class _AsyncRedisGuard:
    """Proxy that force-exits on fatal Redis errors for async calls."""

    def __init__(self, client: object) -> None:
        self._client = client
        self._fatal = _redis_fatal_exceptions()

    def __getattr__(self, name: str) -> object:
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        async def guarded(*args: object, **kwargs: object) -> object:
            try:
                result = attr(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            except self._fatal as e:
                _force_exit(e, name)
                raise  # pragma: no cover - unreachable after os._exit
            return result

        return guarded

    def __getitem__(self, key: object) -> object:
        return self._client[key]

    def __setitem__(self, key: object, value: object) -> None:
        self._client[key] = value


def get_redis_sync_client() -> object | None:
    """Return the initialized sync Redis client, if object."""
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
        logger.exception("Redis connection error at %s", redis_uri)
        raise RedisConnectionError("Failed to connect to Redis") from e

    _redis_sync_client = _SyncRedisGuard(redis_sync)
    _redis_async_client = _AsyncRedisGuard(redis_async)
    return _redis_sync_client, _redis_async_client


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
        logger.exception("Redis readiness check failed")
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
