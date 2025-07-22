import asyncio
import functools
import json
import logging
import time
from collections.abc import Callable

import json_advanced


def get_all_subclasses(cls: type) -> list[type]:
    subclasses = cls.__subclasses__()
    return subclasses + [
        sub for subclass in subclasses for sub in get_all_subclasses(subclass)
    ]


def parse_array_parameter(value: object) -> list:
    """Parse input value into a list, handling various input formats.

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
    """Extract the base field name by removing suffixes."""
    if field.endswith("_from"):
        return field[:-5]
    elif field.endswith("_to"):
        return field[:-3]
    elif field.endswith("_in"):
        return field[:-3]
    elif field.endswith("_nin"):
        return field[:-4]
    return field


def is_valid_range_value(value: object) -> bool:
    """Check if value is valid for range comparison."""
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
    if len(args) > 0:
        if inspect.ismethod(func) or inspect.isfunction(func):
            if hasattr(args[0], "__class__"):
                class_name = args[0].__class__.__name__
                func_name = f"{class_name}.{func_name}"
    traceback_str = "".join(traceback.format_tb(e.__traceback__))
    logging.error(
        f"An error occurred in {func_name} ({args=}, {kwargs=}):\n"
        f"{traceback_str}\n{type(e)}: {e}"
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
    if sync_to_thread or asyncio.iscoroutinefunction(func):
        return _async_try_except_wrapper(func)
    return _sync_try_except_wrapper(func)


def delay_execution(seconds: int, sync_to_thread: bool = False) -> Callable:
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
                    f"Attempt {attempt + 1} failed for {func.__name__}: {e}"
                )
                if delay > 0 and attempt < attempts - 1:
                    await asyncio.sleep(delay)
        logging.error(f"All {attempts} attempts failed for {func.__name__}")
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
                    f"Attempt {attempt + 1} failed for {func.__name__}: {e}"
                )
                if delay > 0 and attempt < attempts - 1:
                    time.sleep(delay)
        logging.error(f"All {attempts} attempts failed for {func.__name__}")
        raise last_exception

    return wrapper


def retry_execution(
    attempts: int, delay: int = 0, sync_to_thread: bool = False
) -> Callable[[Callable], Callable]:
    def decorator(func: Callable) -> Callable:
        if sync_to_thread or asyncio.iscoroutinefunction(func):
            return _async_retry_wrapper(func, attempts, delay)
        return _sync_retry_wrapper(func, attempts, delay)

    return decorator
