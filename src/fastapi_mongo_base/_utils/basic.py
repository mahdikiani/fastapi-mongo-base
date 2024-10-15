import asyncio
import functools
import logging


def get_all_subclasses(cls: type):
    subclasses = cls.__subclasses__()
    return subclasses + [
        sub for subclass in subclasses for sub in get_all_subclasses(subclass)
    ]


def try_except_wrapper(func):
    @functools.wraps(func)
    async def wrapped_func(*args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)
        except Exception as e:
            import inspect
            import traceback

            func_name = func.__name__
            if len(args) > 0:
                if inspect.ismethod(func) or inspect.isfunction(func):
                    if hasattr(args[0], "__class__"):
                        class_name = args[0].__class__.__name__
                        func_name = f"{class_name}.{func_name}"

            traceback_str = "".join(traceback.format_tb(e.__traceback__))
            logging.error(f"An error occurred in {func_name}:\n{traceback_str}\n{e}")
            return None

    return wrapped_func


def delay_execution(seconds):
    def decorator(func):
        @functools.wraps(func)
        async def wrapped_func(*args, **kwargs):
            await asyncio.sleep(seconds)
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return await asyncio.to_thread(func, *args, **kwargs)

        return wrapped_func

    return decorator


def retry_execution(attempts, delay=0):
    def decorator(func):
        @functools.wraps(func)
        async def wrapped_func(*args, **kwargs):
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
            # If the loop finishes and the function didn't return successfully
            logging.error(f"All {attempts} attempts failed for {func.__name__}")
            raise last_exception

        return wrapped_func

    return decorator
