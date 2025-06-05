import asyncio
import functools
import json
import logging
import time
from typing import Any

import json_advanced


def get_all_subclasses(cls: type):
    subclasses = cls.__subclasses__()
    return subclasses + [
        sub for subclass in subclasses for sub in get_all_subclasses(subclass)
    ]


def parse_array_parameter(value: Any) -> list:
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
    return list(set([v.strip() for v in value.split(",") if v.strip()]))


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


def is_valid_range_value(value) -> bool:
    """Check if value is valid for range comparison."""
    from datetime import date, datetime
    from decimal import Decimal

    return isinstance(value, (int, float, Decimal, datetime, date, str))


def try_except_wrapper(func, sync_to_thread=False):
    def exception_handler(*, e: Exception, args, kwargs):
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

    @functools.wraps(func)
    async def awrapped_func(*args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            return exception_handler(e=e, args=args, kwargs=kwargs)

    @functools.wraps(func)
    def wrapped_func(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return exception_handler(e=e, args=args, kwargs=kwargs)

    if sync_to_thread or asyncio.iscoroutinefunction(func):
        return awrapped_func
    return wrapped_func


def delay_execution(seconds, sync_to_thread=False):
    def decorator(func):
        @functools.wraps(func)
        async def awrapped_func(*args, **kwargs):
            await asyncio.sleep(seconds)
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            time.sleep(seconds)
            return func(*args, **kwargs)

        if sync_to_thread or asyncio.iscoroutinefunction(func):
            return awrapped_func
        return wrapped_func

    return decorator


def retry_execution(attempts, delay=0, sync_to_thread=False):
    def decorator(func):
        @functools.wraps(func)
        async def awrapped_func(*args, **kwargs):
            last_exception = None
            for attempt in range(attempts):
                try:
                    if asyncio.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    return await asyncio.to_thread(func, *args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logging.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: "
                        f"{e}"
                    )
                    if delay > 0 and attempt < attempts - 1:
                        await asyncio.sleep(delay)
            # If the loop finishes and the function didn't return successfully
            logging.error(
                f"All {attempts} attempts failed for {func.__name__}"
            )
            raise last_exception

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            last_exception = None
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logging.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: "
                        f"{e}"
                    )
                    if delay > 0 and attempt < attempts - 1:
                        time.sleep(delay)
            # If the loop finishes and the function didn't return successfully
            logging.error(
                f"All {attempts} attempts failed for {func.__name__}"
            )
            raise last_exception

        if sync_to_thread or asyncio.iscoroutinefunction(func):
            return awrapped_func
        return wrapped_func

    return decorator
