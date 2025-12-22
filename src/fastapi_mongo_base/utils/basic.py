"""
Basic utility functions for async operations, retries, and error handling.

This module provides decorators and helpers for common async patterns.
"""

import asyncio
import functools
import json
import logging
import time
from collections.abc import Callable, Coroutine

import json_advanced

FunctionOrCoroutine = (
    Callable[..., None] | Callable[..., Coroutine[object, object, None]]
)


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
            parsed = json_advanced.loads(value)
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
        field = field.split(".")[0]
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
    func: Callable,
    e: Exception,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    import inspect
    import traceback

    func_name = func.__name__
    if (
        len(args) > 0
        and (inspect.ismethod(func) or inspect.isfunction(func))
        and hasattr(args[0], "__class__")
    ):
        class_name = args[0].__class__.__name__
        func_name = f"{class_name}.{func_name}"
    traceback_str = "".join(traceback.format_tb(e.__traceback__))
    logging.error(
        "An error occurred in %s (%s=, %s):\n%s\n%s: %s",
        func_name,
        args,
        kwargs,
        traceback_str,
        type(e),
        e,
    )
    return None


def _async_try_except_wrapper(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> object:
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            return _exception_handler(func, e, args, kwargs)

    return wrapper


def _sync_try_except_wrapper(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return _exception_handler(func, e, args, kwargs)

    return wrapper


def try_except_wrapper(
    func: Callable,
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
    if sync_to_thread or asyncio.iscoroutinefunction(func):
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
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)

        @functools.wraps(func)
        def wrapped_func(*args: object, **kwargs: object) -> object:
            time.sleep(seconds)
            return func(*args, **kwargs)

        if sync_to_thread or asyncio.iscoroutinefunction(func):
            return awrapped_func
        return wrapped_func

    return decorator


def _async_retry_wrapper(
    func: Callable, attempts: int, delay: int
) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: object, **kwargs: object) -> object:
        last_exception = None
        for attempt in range(attempts):
            try:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return await asyncio.to_thread(func, *args, **kwargs)
            except Exception as e:
                last_exception = e
                logging.warning(
                    "Attempt %d failed for %s: %s",
                    attempt + 1,
                    func.__name__,
                    e,
                )
                if delay > 0 and attempt < attempts - 1:
                    await asyncio.sleep(delay)
        logging.error("All %d attempts failed for %s", attempts, func.__name__)
        raise last_exception

    return wrapper


def _sync_retry_wrapper(func: Callable, attempts: int, delay: int) -> Callable:
    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        last_exception = None
        for attempt in range(attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logging.warning(
                    "Attempt %d failed for %s: %s",
                    attempt + 1,
                    func.__name__,
                    e,
                )
                if delay > 0 and attempt < attempts - 1:
                    time.sleep(delay)
        logging.error("All %d attempts failed for %s", attempts, func.__name__)
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
        if sync_to_thread or asyncio.iscoroutinefunction(func):
            return _async_retry_wrapper(func, attempts, delay)
        return _sync_retry_wrapper(func, attempts, delay)

    return decorator


async def gather_sync(
    coroutines: list[Callable[..., Coroutine[object, object, object]]],
    /,
    sync: bool = False,
) -> list[object]:
    """
    Execute coroutines in parallel or sequentially.

    Args:
        coroutines: List of coroutines to execute.
        sync: If True, execute sequentially; if False, execute in parallel.

    Returns:
        List of results from coroutines.

    """
    if sync:
        return [await coroutine for coroutine in coroutines]
    return await asyncio.gather(*coroutines)
