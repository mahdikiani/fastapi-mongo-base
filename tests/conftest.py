import logging
import os
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from src.fastapi_mongo_base import models as base_mongo_models
from src.fastapi_mongo_base.utils import basic

from .app.server import Settings
from .app.server import app as fastapi_app


@pytest.fixture(scope="session", autouse=True)
def setup_debugpy() -> None:
    if os.getenv("DEBUGPY", "False").lower() in ("true", "1", "yes"):
        import debugpy  # noqa: T100

        debugpy.listen(("127.0.0.1", 3020))  # noqa: T100
        debugpy.wait_for_client()  # noqa: T100


@pytest_asyncio.fixture(scope="session")
async def mongo_client() -> AsyncGenerator[AsyncMongoMockClient]:
    mongo_client = AsyncMongoMockClient()
    yield mongo_client


# Async setup function to initialize the database with Beanie
async def init_db(mongo_client: AsyncMongoMockClient) -> None:
    database = mongo_client.get_database("test_db")
    await init_beanie(
        database=database,
        document_models=basic.get_all_subclasses(base_mongo_models.BaseEntity),
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def db(mongo_client: AsyncMongoMockClient) -> AsyncGenerator[None]:
    Settings.config_logger()
    logging.info("Initializing database")
    await init_db(mongo_client)
    logging.info("Database initialized")
    yield
    logging.info("Cleaning up database")


@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    """Fixture to provide an AsyncClient for FastAPI app."""

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://test.usso.io",
    ) as ac:
        yield ac
