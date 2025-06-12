import asyncio
import logging
from collections import deque
from contextlib import asynccontextmanager

import fastapi
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, exceptions


async def health(request: fastapi.Request):
    return {"status": "up"}


@asynccontextmanager
async def lifespan(
    *,
    app: fastapi.FastAPI,
    worker=None,
    init_functions=None,
    settings: config.Settings = None,
):
    """Initialize application services."""
    if init_functions is None:
        init_functions = []
    await db.init_mongo_db(settings)

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


def setup_exception_handlers(
    *, app: fastapi.FastAPI, handlers: dict = None, **kwargs
):
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


def get_app_kwargs(
    *,
    settings: config.Settings | None = None,
    title=None,
    description=None,
    version="0.1.0",
    lifespan_func=None,
    worker=None,
    init_functions: list | None = None,
    contact=None,
    license_info=None,
    **kwargs,
):
    if license_info is None:
        license_info = {
            "name": "MIT License",
            "url": "https://github.com/mahdikiani/FastAPILaunchpad/blob/main/LICENSE",  # noqa: E501
        }
    if init_functions is None:
        init_functions = []
    settings.config_logger()

    """Create a FastAPI app with shared configurations."""
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

        def lifespan_func(app):
            return lifespan(
                app=app,
                worker=worker,
                init_functions=init_functions,
                settings=settings,
            )

    docs_url = f"{base_path}/docs"
    openapi_url = f"{base_path}/openapi.json"
    redoc_url = f"{base_path}/redoc"
    return dict(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan_func,
        contact=contact,
        license_info=license_info,
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=redoc_url,
    )


def create_app(
    settings: config.Settings = None,
    *,
    title=None,
    description=None,
    version="0.1.0",
    serve_coverage: bool = False,
    origins: list = None,
    lifespan_func=None,
    worker=None,
    init_functions: list | None = None,
    contact=None,
    license_info=None,
    exception_handlers: dict = None,
    log_route: bool = False,
    health_route: bool = True,
    index_route: bool = True,
    **kwargs,
) -> fastapi.FastAPI:
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
    settings: config.Settings = None,
    *,
    serve_coverage: bool = False,
    origins: list = None,
    exception_handlers: dict = None,
    log_route: bool = False,
    health_route: bool = True,
    index_route: bool = True,
    **kwargs,
) -> fastapi.FastAPI:
    base_path: str = settings.base_path
    setup_exception_handlers(app=app, handlers=exception_handlers, **kwargs)
    setup_middlewares(app=app, origins=origins, **kwargs)

    if origins is None:
        origins = ["http://localhost:8000"]

    async def logs():
        with open(settings.get_log_config()["info_log_path"], "rb") as f:
            last_100_lines = deque(f, maxlen=100)

        return [line.decode("utf-8") for line in last_100_lines]

    async def index(request: fastapi.Request):
        return RedirectResponse(url=f"{base_path}/docs")

    if health_route:
        app.get(f"{base_path}/health")(health)
    if log_route:
        app.get(f"{base_path}/logs", include_in_schema=False)(logs)
    if index_route:
        app.get("/", include_in_schema=False)(index)

    if serve_coverage:
        app.mount(
            f"{settings.base_path}/coverage",
            StaticFiles(directory=settings.get_coverage_dir()),
            name="coverage",
        )

    return app
