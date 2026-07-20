"""FastAPI application factory and configuration."""

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import fastapi
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..errors.handlers import EXCEPTION_HANDLERS
from ..errors.responses import COMMON_ERROR_RESPONSES, setup_openapi_errors
from ..monitoring.sentry import setup_sentry
from . import config, db


def _is_configured_uri(value: str | None) -> bool:
    return bool(value and str(value).strip())


def _use_mongodb(settings: config.Settings | None) -> bool:
    if settings is None:
        return False
    try:
        import beanie  # noqa: F401
    except ImportError:
        return False
    return _is_configured_uri(getattr(settings, "mongo_uri", None))


def _use_redis(settings: config.Settings | None) -> bool:
    if settings is None:
        return False
    try:
        import redis  # noqa: F401
    except ImportError:
        return False
    return _is_configured_uri(getattr(settings, "redis_uri", None))


def _use_sql(settings: config.Settings | None) -> bool:
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        return False

    if settings is None:
        return False
    return _is_configured_uri(getattr(settings, "database_uri", None))


def health(request: fastapi.Request) -> dict[str, object]:
    """
    Liveness probe endpoint handler.

    Args:
        request: FastAPI request object.

    Returns:
        Dictionary with status and optional version.

    """
    payload: dict[str, object] = {"status": "up"}

    return payload


async def readiness(request: fastapi.Request) -> JSONResponse:
    """
    Readiness probe endpoint handler.

    Args:
        request: FastAPI request object.

    Returns:
        JSON response with dependency checks and HTTP 503 when degraded.

    """
    datasources = getattr(request.app.state, "datasources", {})
    mongo_client = getattr(request.app.state, "mongo_client", None)
    redis_client = getattr(request.app.state, "redis_async_client", None)
    sql_session = getattr(request.app.state, "async_session", None)

    checks: dict[str, str] = {}
    if datasources.get("mongodb"):
        checks["mongodb"] = await db.check_mongodb(mongo_client)

    if datasources.get("redis"):
        checks["redis"] = await db.check_redis(redis_client)

    if datasources.get("sql"):
        checks["sql"] = await db.check_sql(sql_session)

    is_ready = "down" not in checks.values()
    payload: dict[str, object] = {
        "status": "up" if is_ready else "degraded",
        "checks": checks,
    }
    if request.app.version:
        payload["version"] = request.app.version

    return JSONResponse(
        status_code=fastapi.status.HTTP_200_OK
        if is_ready
        else fastapi.status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload,
    )


async def _startup_datasources(
    app: fastapi.FastAPI,
    settings: config.Settings | None,
) -> None:
    use_mongo = _use_mongodb(settings)
    use_redis = _use_redis(settings)
    use_sql = _use_sql(settings)
    app.state.datasources = {
        "mongodb": use_mongo,
        "redis": use_redis,
        "sql": use_sql,
    }

    if use_mongo:
        mongo_db, mongo_client = await db.init_mongo_db(settings)
    else:
        mongo_db, mongo_client = None, None
    app.state.mongo_db = mongo_db
    app.state.mongo_client = mongo_client

    if use_redis:
        redis_sync, redis_async = db.init_redis(settings)
    else:
        redis_sync, redis_async = None, None
    app.state.redis_sync_client = redis_sync
    app.state.redis_async_client = redis_async

    if use_sql:
        sql_engine, sql_session = await db.init_sql(settings)
    else:
        sql_engine, sql_session = None, None
    app.state.sql_engine = sql_engine
    app.state.async_session = sql_session


async def _shutdown_datasources(app: fastapi.FastAPI) -> None:
    if getattr(app.state, "mongo_client", None) is not None:
        await db.close_mongo_client(app.state.mongo_client)
    if (
        getattr(app.state, "redis_sync_client", None) is not None
        or getattr(app.state, "redis_async_client", None) is not None
    ):
        await db.close_redis(
            getattr(app.state, "redis_sync_client", None),
            getattr(app.state, "redis_async_client", None),
        )
    if getattr(app.state, "sql_engine", None) is not None:
        await db.close_sql(app.state.sql_engine)


@asynccontextmanager
async def lifespan(
    *,
    app: fastapi.FastAPI,
    worker: Callable[[], object] | None = None,
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
    if settings is not None:
        app.state.settings = settings

    await _startup_datasources(app, settings)

    if worker:
        app.state.worker = asyncio.create_task(worker())

    for function in init_functions:
        if inspect.iscoroutinefunction(function):
            await function()
        else:
            function()

    logging.info("Startup complete")
    try:
        yield
    finally:
        if worker:
            app.state.worker.cancel()
        await _shutdown_datasources(app)
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
    exception_handlers = EXCEPTION_HANDLERS
    if handlers:
        exception_handlers.update(handlers)

    for exc_class, handler in exception_handlers.items():
        app.exception_handler(exc_class)(handler)


def setup_middlewares(
    *,
    app: fastapi.FastAPI,
    origins: list | None = None,
    timezone_middleware: bool = True,
    **kwargs: object,
) -> None:
    """
    Configure middleware for the FastAPI application.

    Args:
        app: FastAPI application instance.
        origins: Optional list of allowed CORS origins.
        timezone_middleware: Whether to enable request timezone middleware.
        **kwargs: Additional keyword arguments.

    """
    from fastapi.middleware.cors import CORSMiddleware

    if timezone_middleware:
        from ..middlewares.timezone import TimezoneMiddleware

        app.add_middleware(TimezoneMiddleware)

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
    lifespan_func: Callable[[fastapi.FastAPI], object] | None = None,
    worker: Callable[[], object] | None = None,
    init_functions: list | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
    **kwargs: object,
) -> dict[str, object]:
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
    setup_sentry(settings)

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
    lifespan_func: Callable[[fastapi.FastAPI], object] | None = None,
    worker: Callable[[], object] | None = None,
    init_functions: list | None = None,
    contact: dict[str, str] | None = None,
    license_info: dict[str, str] | None = None,
    exception_handlers: dict | None = None,
    log_route: bool = False,
    health_route: bool = True,
    readiness_route: bool = True,
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
        health_route: Whether to enable liveness health check route.
        readiness_route: Whether to enable readiness health check route.
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

    app = fastapi.FastAPI(
        **data,
        responses=kwargs.pop("responses", COMMON_ERROR_RESPONSES),
    )

    app = configure_app(
        app=app,
        settings=settings,
        origins=origins,
        serve_coverage=serve_coverage,
        exception_handlers=exception_handlers,
        log_route=log_route,
        health_route=health_route,
        readiness_route=readiness_route,
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
    readiness_route: bool = True,
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
        health_route: Whether to enable liveness health check route.
        readiness_route: Whether to enable readiness health check route.
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
    if readiness_route:
        app.get(f"{base_path}/ready")(readiness)
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

    setup_openapi_errors(app)

    return app
