"""
Basic utility functions for async operations, retries, and error handling.

This module provides decorators and helpers for common async patterns.
"""

import asyncio
import functools
import inspect
import json
import logging
import time
from collections.abc import Awaitable, Callable
from types import ModuleType
from typing import Any, TypeVar, cast


def _json_codec() -> ModuleType:
    """Return json_advanced when installed, otherwise stdlib json."""
    try:
        import json_advanced
    except ImportError:
        return json
    return json_advanced


json_codec = _json_codec()

logger = logging.getLogger(__name__)


FunctionOrCoroutine = Callable[..., object]


def get_all_subclasses(cls: type) -> list[type]:
    """
    Recursively get all subclasses of a class.

    Args:
        cls: Base class to find subclasses for.

    Returns:
        List of all subclasses (including nested subclasses).

    """
    subclasses = cls.__subclasses__()
    return subclasses + [
        sub for subclass in subclasses for sub in get_all_subclasses(subclass)
    ]


def parse_array_parameter(value: object) -> list:
    """
    Parse input value into a list, handling various input formats.

    Args:
        value: Input value that could be a JSON string, comma-separated string,
                list, tuple, or single value

    Returns:
        list: Parsed list of values

    """
    if isinstance(value, (list, tuple)):
        return list(set(value))

    if not isinstance(value, str):
        return [value]

    # Try parsing as JSON first
    value = value.strip()
    try:
        if value.startswith("[") and value.endswith("]"):
            parsed = json_codec.loads(value)
            if isinstance(parsed, list):
                return list(set(parsed))
            return [parsed]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback to comma-separated values
    return list({v.strip() for v in value.split(",") if v.strip()})


def get_base_field_name(field: str) -> str:
    """
    Extract the base field name by removing query suffixes.

    Args:
        field: Field name with optional suffix (e.g., "created_at_from").

    Returns:
        Base field name without suffix (e.g., "created_at").

    """
    suffixes = [
        "_from",
        "_to",
        "_in",
        "_nin",
        "_ne",
        "_eq",
        "_gt",
        "_gte",
        "_lt",
        "_lte",
        "_like",
    ]
    if "." in field:
        field = field.split(".", maxsplit=1)[0]
    for suffix in suffixes:
        if field.endswith(suffix):
            return field[: -len(suffix)]

    return field


def is_valid_range_value(value: object) -> bool:
    """
    Check if value is valid for range comparison operations.

    Args:
        value: Value to check.

    Returns:
        True if value can be used in range queries, False otherwise.

    """
    from datetime import date, datetime
    from decimal import Decimal

    return isinstance(value, (int, float, Decimal, datetime, date, str))


def _exception_handler(
    func: Callable[..., Any],
    e: Exception,
    args: tuple[object, ...],
    kwargs: dict[str, Any],
) -> None:
    import inspect
    import traceback

    func_name = getattr(func, "__name__", repr(func))
    if (
        len(args) > 0
        and (inspect.ismethod(func) or inspect.isfunction(func))
        and hasattr(args[0], "__class__")
    ):
        class_name = args[0].__class__.__name__
        func_name = f"{class_name}.{func_name}"
    traceback_str = "".join(traceback.format_tb(e.__traceback__))
    logger.error(
        "An error occurred in %s (%s=, %s):\n%s\n%s: %s",
        func_name,
        args,
        kwargs,
        traceback_str,
        type(e),
        e,
    )


def _async_try_except_wrapper(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> object:
        try:
            if inspect.iscoroutinefunction(func):
                return await func(*args, **cast("Any", kwargs))
            return await asyncio.to_thread(func, *args, **cast("Any", kwargs))
        except Exception as e:
            _exception_handler(func, e, args, kwargs)
            return None

    return wrapper


def _sync_try_except_wrapper(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return func(*args, **cast("Any", kwargs))
        except Exception as e:
            _exception_handler(func, e, args, kwargs)
            return None

    return wrapper


def try_except_wrapper(
    func: Callable[..., Any],
    sync_to_thread: bool = False,
) -> Callable:
    """
    Wrap a function with try-except error handling.

    Args:
        func: Function to wrap.
        sync_to_thread: Whether to run sync functions in thread pool.

    Returns:
        Wrapped function with error handling.

    """
    if sync_to_thread or inspect.iscoroutinefunction(func):
        return _async_try_except_wrapper(func)
    return _sync_try_except_wrapper(func)


def delay_execution(seconds: int, sync_to_thread: bool = False) -> Callable:
    """
    Delay function execution by specified seconds.

    Args:
        seconds: Number of seconds to delay.
        sync_to_thread: Whether to run sync functions in thread pool.

    Returns:
        Decorator function.

    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def awrapped_func(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(seconds)
            if inspect.iscoroutinefunction(func):
                return await func(*args, **cast("Any", kwargs))
            return await asyncio.to_thread(func, *args, **cast("Any", kwargs))

        @functools.wraps(func)
        def wrapped_func(*args: object, **kwargs: object) -> object:
            time.sleep(seconds)
            return func(*args, **cast("Any", kwargs))

        if sync_to_thread or inspect.iscoroutinefunction(func):
            return awrapped_func
        return wrapped_func

    return decorator


async def _run_async_attempt(
    func: Callable[..., Any],
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    if inspect.iscoroutinefunction(func):
        return await func(*args, **cast("Any", kwargs))
    return await asyncio.to_thread(func, *args, **cast("Any", kwargs))


def _async_retry_wrapper(
    func: Callable[..., Any], attempts: int, delay: int
) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> object:
        last_exception: Exception | None = None
        for attempt in range(attempts):
            result, last_exception = await _async_attempt_once(
                func, args, kwargs, attempt, attempts, delay
            )
            if result is not _RETRY_SENTINEL:
                return result
        logger.error(
            "All %d attempts failed for %s",
            attempts,
            getattr(func, "__name__", repr(func)),
        )
        if last_exception is None:
            raise RuntimeError("Retry failed without capturing an exception")
        raise last_exception

    return wrapper


_RETRY_SENTINEL = object()


async def _async_attempt_once(
    func: Callable[..., Any],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    attempt: int,
    attempts: int,
    delay: int,
) -> tuple[object, Exception | None]:
    try:
        return await _run_async_attempt(func, args, kwargs), None
    except Exception as e:
        logger.warning(
            "Attempt %d failed for %s: %s",
            attempt + 1,
            getattr(func, "__name__", repr(func)),
            e,
        )
        if delay > 0 and attempt < attempts - 1:
            await asyncio.sleep(delay)
        return _RETRY_SENTINEL, e


def _sync_attempt_once(
    func: Callable[..., Any],
    args: tuple[object, ...],
    kwargs: dict[str, object],
    attempt: int,
    attempts: int,
    delay: int,
) -> tuple[object, Exception | None]:
    try:
        return func(*args, **cast("Any", kwargs)), None
    except Exception as e:
        logger.warning(
            "Attempt %d failed for %s: %s",
            attempt + 1,
            getattr(func, "__name__", repr(func)),
            e,
        )
        if delay > 0 and attempt < attempts - 1:
            time.sleep(delay)
        return _RETRY_SENTINEL, e


def _sync_retry_wrapper(
    func: Callable[..., Any], attempts: int, delay: int
) -> Callable:
    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        last_exception: Exception | None = None
        for attempt in range(attempts):
            result, err = _sync_attempt_once(
                func, args, kwargs, attempt, attempts, delay
            )
            if err is None:
                return result
            last_exception = err
        logger.error(
            "All %d attempts failed for %s",
            attempts,
            getattr(func, "__name__", repr(func)),
        )
        if last_exception is None:
            raise RuntimeError("Retry failed without capturing an exception")
        raise last_exception

    return wrapper


def retry_execution(
    attempts: int, delay: int = 0, sync_to_thread: bool = False
) -> Callable[[Callable], Callable]:
    """
    Retry function execution on failure.

    Args:
        attempts: Number of retry attempts.
        delay: Delay in seconds between attempts.
        sync_to_thread: Whether to run sync functions in thread pool.

    Returns:
        Decorator function.

    """

    def decorator(func: Callable) -> Callable:
        if sync_to_thread or inspect.iscoroutinefunction(func):
            return _async_retry_wrapper(func, attempts, delay)
        return _sync_retry_wrapper(func, attempts, delay)

    return decorator


async def gather_sync(
    coroutines: list[Awaitable[Any]],
    /,
    sync: bool = False,
) -> list[Any]:
    """
    Execute coroutines in parallel or sequentially.

    Args:
        coroutines: List of awaitables to execute.
        sync: If True, execute sequentially; if False, execute in parallel.

    Returns:
        List of results from coroutines.

    """
    if sync:
        return [await coroutine for coroutine in coroutines]
    return list(await asyncio.gather(*coroutines))


R = TypeVar("R")


def _resolve_mock(
    return_value: R | Callable[..., R | Awaitable[R]],
    *args: object,
    **kwargs: object,
) -> R | Awaitable[R]:
    if callable(return_value):
        return cast("Callable[..., R | Awaitable[R]]", return_value)(
            *args, **cast("Any", kwargs)
        )
    return return_value


def debug_mode_mock(
    return_value: R | Callable[..., R | Awaitable[R]],
) -> Callable[
    [Callable[..., R | Awaitable[R]]], Callable[..., R | Awaitable[R]]
]:
    """
    Return a mock response if debug is enabled.

    Args:
        return_value: The mock response to return if debug is enabled.

    Returns:
        A decorator that returns a mock response if debug is enabled.

    """

    def decorator(
        func: Callable[..., R | Awaitable[R]],
    ) -> Callable[..., R | Awaitable[R]]:

        from fastapi_mongo_base.core.config import Settings

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> R:
            if Settings.debug:
                result = _resolve_mock(
                    return_value, *args, **cast("Any", kwargs)
                )
                if inspect.isawaitable(result):
                    return cast("R", await result)
                return cast("R", result)
            result = func(*args, **cast("Any", kwargs))
            if inspect.isawaitable(result):
                return cast("R", await result)
            return cast("R", result)

        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> R:
            if Settings.debug:
                result = _resolve_mock(
                    return_value, *args, **cast("Any", kwargs)
                )
                if isinstance(result, Awaitable):
                    msg = (
                        "debug_mode_mock callable returned "
                        "Awaitable for sync function"
                    )
                    raise TypeError(msg)
                return cast("R", result)
            return cast("R", func(*args, **cast("Any", kwargs)))

        return (
            async_wrapper
            if inspect.iscoroutinefunction(func)
            else sync_wrapper
        )

    return decorator
