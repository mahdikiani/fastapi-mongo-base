"""FastAPI application factory and configuration."""

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

import fastapi
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, exceptions


def health(request: fastapi.Request) -> dict[str, str]:
    """
    Health check endpoint handler.

    Args:
        request: FastAPI request object.

    Returns:
        Dictionary with status "up".

    """
    return {"status": "up"}


@asynccontextmanager
async def lifespan(
    *,
    app: fastapi.FastAPI,
    worker: Callable[[], Any] | None = None,
    init_functions: list | None = None,
    settings: config.Settings | None = None,
) -> AsyncGenerator[None]:
    """
    Initialize application services and manage application lifecycle.

    Args:
        app: FastAPI application instance.
        worker: Optional worker coroutine to run in background.
        init_functions: Optional list of initialization functions to run.
        settings: Optional settings instance.

    Yields:
        None: Control is yielded to the application runtime.

    """
    if init_functions is None:
        init_functions = []
    await db.init_mongo_db(settings)

    if worker:
        app.state.worker = asyncio.create_task(worker())

    for function in init_functions:
        if inspect.iscoroutinefunction(function):
            await function()
        else:
            function()

    logging.info("Startup complete")
    yield
    if worker:
        app.state.worker.cancel()
    logging.info("Shutdown complete")


def setup_exception_handlers(
    *, app: fastapi.FastAPI, handlers: dict | None = None, **kwargs: object
) -> None:
    """
    Configure exception handlers for the FastAPI application.

    Args:
        app: FastAPI application instance.
        handlers: Optional dictionary of custom exception handlers.
        **kwargs: Additional keyword arguments.

    """
    exception_handlers = exceptions.EXCEPTION_HANDLERS
    if handlers:
        exception_handlers.update(handlers)

    for exc_class, handler in exception_handlers.items():
        app.exception_handler(exc_class)(handler)


def setup_middlewares(
    *, app: fastapi.FastAPI, origins: list | None = None, **kwargs: object
) -> None:
    """
    Configure CORS middleware for the FastAPI application.

    Args:
        app: FastAPI application instance.
        origins: Optional list of allowed CORS origins.
        **kwargs: Additional keyword arguments.

    """
    from fastapi.middleware.cors import CORSMiddleware

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def get_app_kwargs(
    *,
    settings: config.Settings,
    title: str | None = None,
    description: str | None = None,
    version: str = "0.1.0",
    lifespan_func: Callable[[fastapi.FastAPI], Any] | None = None,
    worker: Callable[[], Any] | None = None,
    init_functions: list | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
    **kwargs: object,
) -> dict[str, Any]:
    """
    Generate keyword arguments for FastAPI app creation.

    Args:
        settings: Application settings instance.
        title: Optional application title.
        description: Optional application description.
        version: Application version string.
        lifespan_func: Optional lifespan function.
        worker: Optional worker coroutine.
        init_functions: Optional list of initialization functions.
        contact: Optional contact information dictionary.
        license_info: Optional license information dictionary.
        **kwargs: Additional keyword arguments.

    Returns:
        Dictionary of keyword arguments for FastAPI app creation.

    """
    if license_info is None:
        license_info = {
            "name": "MIT License",
            "url": (
                "https://github.com/mahdikiani"
                "/FastAPILaunchpad/blob/main/LICENSE"
            ),
        }
    if init_functions is None:
        init_functions = []

    settings.config_logger()

    if settings is None:
        settings = config.Settings()
    if title is None:
        title = settings.project_name.replace("-", " ").title()
    if description is None:
        description = getattr(settings, "project_description", None)
    if version is None:
        version = getattr(settings, "project_version", "0.1.0")

    base_path: str = settings.base_path

    if lifespan_func is None:

        def lf(app: fastapi.FastAPI) -> AsyncGenerator[None]:
            return lifespan(
                app=app,
                worker=worker,
                init_functions=init_functions,
                settings=settings,
            )

        lifespan_func = lf

    docs_url = f"{base_path}/docs"
    openapi_url = f"{base_path}/openapi.json"
    redoc_url = f"{base_path}/redoc"
    return {
        "title": title,
        "version": version,
        "description": description,
        "lifespan": lifespan_func,
        "contact": contact,
        "license_info": license_info,
        "docs_url": docs_url,
        "openapi_url": openapi_url,
        "redoc_url": redoc_url,
    }


def create_app(
    settings: config.Settings,
    *,
    title: str | None = None,
    description: str | None = None,
    version: str = "0.1.0",
    serve_coverage: bool = False,
    origins: list | None = None,
    lifespan_func: Callable[[fastapi.FastAPI], Any] | None = None,
    worker: Callable[[], Any] | None = None,
    init_functions: list | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
    exception_handlers: dict | None = None,
    log_route: bool = False,
    health_route: bool = True,
    index_route: bool = True,
    **kwargs: object,
) -> fastapi.FastAPI:
    """
    Create and configure a FastAPI application instance.

    Args:
        settings: Application settings instance.
        title: Optional application title.
        description: Optional application description.
        version: Application version string.
        serve_coverage: Whether to serve coverage reports.
        origins: Optional list of allowed CORS origins.
        lifespan_func: Optional lifespan function.
        worker: Optional worker coroutine.
        init_functions: Optional list of initialization functions.
        contact: Optional contact information dictionary.
        license_info: Optional license information dictionary.
        exception_handlers: Optional exception handlers dictionary.
        log_route: Whether to enable log viewing route.
        health_route: Whether to enable health check route.
        index_route: Whether to enable index redirect route.
        **kwargs: Additional keyword arguments.

    Returns:
        Configured FastAPI application instance.

    """
    if init_functions is None:
        init_functions = []
    data = get_app_kwargs(
        settings=settings,
        title=title,
        description=description,
        version=version,
        origins=origins,
        lifespan_func=lifespan_func,
        worker=worker,
        init_functions=init_functions,
        contact=contact,
        license_info=license_info,
    )

    app = fastapi.FastAPI(**data)

    app = configure_app(
        app=app,
        settings=settings,
        origins=origins,
        serve_coverage=serve_coverage,
        exception_handlers=exception_handlers,
        log_route=log_route,
        health_route=health_route,
        index_route=index_route,
        **kwargs,
    )

    return app


def configure_app(
    app: fastapi.FastAPI,
    settings: config.Settings,
    *,
    serve_coverage: bool = False,
    origins: list | None = None,
    exception_handlers: dict | None = None,
    log_route: bool = False,
    health_route: bool = True,
    index_route: bool = True,
    **kwargs: object,
) -> fastapi.FastAPI:
    """
    Configure routes and middleware for a FastAPI application.

    Args:
        app: FastAPI application instance to configure.
        settings: Application settings instance.
        serve_coverage: Whether to serve coverage reports.
        origins: Optional list of allowed CORS origins.
        exception_handlers: Optional exception handlers dictionary.
        log_route: Whether to enable log viewing route.
        health_route: Whether to enable health check route.
        index_route: Whether to enable index redirect route.
        **kwargs: Additional keyword arguments.

    Returns:
        Configured FastAPI application instance.

    """
    base_path: str = settings.base_path
    if origins is None:
        origins = settings.cors_origins

    setup_exception_handlers(app=app, handlers=exception_handlers, **kwargs)
    setup_middlewares(app=app, origins=origins, **kwargs)

    async def logs() -> list[str]:
        """
        Read the last 100 lines from the log file.

        Returns:
            List of log lines as strings.

        """
        def read_logs() -> list[str]:
            with open(settings.get_log_config()["info_log_path"], "rb") as f:
                last_100_lines = deque(f, maxlen=100)
            return [line.decode("utf-8") for line in last_100_lines]

        return await asyncio.to_thread(read_logs)

    def index(request: fastapi.Request) -> RedirectResponse:
        """
        Redirect root path to API documentation.

        Args:
            request: FastAPI request object.

        Returns:
            Redirect response to /docs endpoint.

        """
        return RedirectResponse(url=f"{base_path}/docs")

    if health_route:
        app.get(f"{base_path}/health")(health)
    if log_route:
        app.get(f"{base_path}/logs", include_in_schema=False)(logs)
    if index_route:
        app.get("/", include_in_schema=False)(index)
        app.get(base_path, include_in_schema=False)(index)

    if serve_coverage:
        app.mount(
            f"{settings.base_path}/coverage",
            StaticFiles(directory=settings.get_coverage_dir()),
            name="coverage",
        )

    return app
