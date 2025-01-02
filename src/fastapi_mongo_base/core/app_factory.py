import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fastapi_mongo_base.core import db, exceptions

try:
    from server.config import Settings
except ImportError:
    from .config import Settings


async def health(request: fastapi.Request):
    return {
        "status": "up",
        "host": request.url.hostname,
        # "host2": request.base_url.hostname,
        # "original_host":request.headers.get("x-original-host", "!not found!"),
        # "forwarded_host": request.headers.get("X-Forwarded-Host", "forwarded_host"),
        # "forwarded_proto": request.headers.get("X-Forwarded-Proto", "forwarded_proto"),
        # "forwarded_for": request.headers.get("X-Forwarded-For", "forwarded_for"),
    }


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI, worker=None, init_functions=[], settings: Settings = None):  # type: ignore
    """Initialize application services."""
    await db.init_mongo_db()

    if worker:
        app.state.worker = asyncio.create_task(worker())

    for function in init_functions:
        if asyncio.iscoroutinefunction(function):
            await function()
        else:
            function()

    logging.info("Startup complete")
    yield
    app.state.worker.cancel()
    logging.info("Shutdown complete")


def setup_exception_handlers(
    app: fastapi.FastAPI,
    usso_handler: bool = True,
    ufaas_handler: bool = True,
    **kwargs,
):
    exception_handlers = exceptions.EXCEPTION_HANDLERS
    if usso_handler:
        from usso.fastapi.integration import (
            EXCEPTION_HANDLERS as USSO_EXCEPTION_HANDLERS,
        )

        exception_handlers.update(USSO_EXCEPTION_HANDLERS)
    if ufaas_handler:
        from ufaas.fastapi.integration import (
            EXCEPTION_HANDLERS as UFAAS_EXCEPTION_HANDLERS,
        )

        exception_handlers.update(UFAAS_EXCEPTION_HANDLERS)

    for exc_class, handler in exception_handlers.items():
        app.exception_handler(exc_class)(handler)


def setup_middlewares(
    app: fastapi.FastAPI,
    origins: list = None,
    original_host_middleware: bool = False,
    request_log_middleware: bool = False,
    **kwargs,
):
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if original_host_middleware:
        from ufaas_fastapi_business.core.middlewares import OriginalHostMiddleware

        app.add_middleware(OriginalHostMiddleware)
    if request_log_middleware:
        from .middlewares import RequestLoggingMiddleware

        app.add_middleware(RequestLoggingMiddleware)


def create_app(
    *,
    settings: Settings = None,
    title=None,
    description=None,
    version="0.1.0",
    serve_coverage: bool = False,
    origins: list = None,
    lifespan_func=None,
    worker=None,
    init_functions: list = [],
    contact={
        "name": "Mahdi Kiani",
        "url": "https://github.com/mahdikiani/FastAPILaunchpad",
        "email": "mahdikiany@gmail.com",
    },
    license_info={
        "name": "MIT License",
        "url": "https://github.com/mahdikiani/FastAPILaunchpad/blob/main/LICENSE",
    },
    usso_handler: bool = True,
    ufaas_handler: bool = True,
    original_host_middleware: bool = False,
    request_log_middleware: bool = False,
    **kwargs,
) -> fastapi.FastAPI:
    settings.config_logger()

    """Create a FastAPI app with shared configurations."""
    if settings is None:
        settings = Settings()
    if title is None:
        title = settings.project_name.replace("-", " ").title()
    if description is None:
        description = getattr(settings, "project_description", None)
    if version is None:
        version = getattr(settings, "project_version", "0.1.0")
    base_path: str = settings.base_path

    if origins is None:
        origins = ["http://localhost:8000"]

    if lifespan_func is None:
        lifespan_func = lambda app: lifespan(app, worker, init_functions, settings)

    docs_url = f"{base_path}/docs"
    openapi_url = f"{base_path}/openapi.json"

    app = fastapi.FastAPI(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan_func,
        contact=contact,
        license_info=license_info,
        docs_url=docs_url,
        openapi_url=openapi_url,
    )

    setup_exception_handlers(app, usso_handler, ufaas_handler, **kwargs)
    setup_middlewares(
        app,
        origins,
        original_host_middleware,
        request_log_middleware,
        **kwargs,
    )

    async def logs():
        with open(settings.get_log_config()["info_log_path"], "rb") as f:
            last_100_lines = deque(f, maxlen=100)

        return [line.decode("utf-8") for line in last_100_lines]

    app.get(f"{base_path}/health")(health)
    app.get(f"{base_path}/logs", include_in_schema=False)(logs)

    if serve_coverage:
        app.mount(
            f"{settings.base_path}/coverage",
            StaticFiles(directory=settings.get_coverage_dir()),
            name="coverage",
        )

    return app
