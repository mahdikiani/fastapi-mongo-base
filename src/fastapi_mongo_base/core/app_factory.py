import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager

import fastapi
from fastapi.staticfiles import StaticFiles

from fastapi_mongo_base.core import db, exceptions

try:
    from server.config import Settings
except ImportError:
    from .config import Settings


async def health(request: fastapi.Request):
    return {"status": "up"}


@asynccontextmanager
async def lifespan(
    *, app: fastapi.FastAPI, worker=None, init_functions=[], settings: Settings = None
):
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
    if worker:
        app.state.worker.cancel()
    logging.info("Shutdown complete")


def setup_exception_handlers(*, app: fastapi.FastAPI, handlers: dict = None, **kwargs):
    exception_handlers = exceptions.EXCEPTION_HANDLERS
    if handlers:
        exception_handlers.update(handlers)

    for exc_class, handler in exception_handlers.items():
        app.exception_handler(exc_class)(handler)


def setup_middlewares(*, app: fastapi.FastAPI, origins: list = None, **kwargs):
    from fastapi.middleware.cors import CORSMiddleware

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

def create_app(
    settings: Settings = None,
    *,
    title=None,
    description=None,
    version="0.1.0",
    serve_coverage: bool = False,
    origins: list = None,
    lifespan_func=None,
    worker=None,
    init_functions: list = [],
    contact=None,
    license_info={
        "name": "MIT License",
        "url": "https://github.com/mahdikiani/FastAPILaunchpad/blob/main/LICENSE",
    },
    exception_handlers: dict = None,
    log_route: bool = False,
    health_route: bool = True,
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

    setup_exception_handlers(app=app, handlers=exception_handlers, **kwargs)
    setup_middlewares(app=app, origins=origins, **kwargs)

    async def logs():
        with open(settings.get_log_config()["info_log_path"], "rb") as f:
            last_100_lines = deque(f, maxlen=100)

        return [line.decode("utf-8") for line in last_100_lines]

    if health_route:
        app.get(f"{base_path}/health")(health)
    if log_route:
        app.get(f"{base_path}/logs", include_in_schema=False)(logs)

    if serve_coverage:
        app.mount(
            f"{settings.base_path}/coverage",
            StaticFiles(directory=settings.get_coverage_dir()),
            name="coverage",
        )

    return app
