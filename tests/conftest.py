"""Shared pytest fixtures for FastAPI MongoDB base package."""

import logging
import os
from collections.abc import AsyncGenerator, Generator

import httpx
import pytest
import pytest_asyncio
from beanie import init_beanie

from src.fastapi_mongo_base import models as base_mongo_models
from src.fastapi_mongo_base.utils import basic

from .app.server import Settings
from .app.server import app as fastapi_app


def pytest_configure(config: pytest.Config) -> None:
    """Set up debugpy when DEBUGPY env var is enabled."""
    if os.getenv("DEBUGPY", "False").lower() in ("true", "1", "yes"):
        import debugpy  # noqa: T100

        debugpy.listen(("127.0.0.1", 3020))  # noqa: T100
        logging.info("Waiting for debugpy client")
        debugpy.wait_for_client()  # noqa: T100


@pytest_asyncio.fixture(scope="session")
def mongo_client() -> Generator:
    """
    Fixture to provide an AsyncMongoMockClient for testing.

    Returns:
        AsyncMongoMockClient.
    """
    from mongomock_motor import AsyncMongoMockClient

    yield AsyncMongoMockClient()


# Async setup function to initialize the database with Beanie
async def init_db(mongo_client: object) -> None:
    """
    Initialize the database with Beanie.

    Args:
        mongo_client: AsyncMongoMockClient.

    Returns:
        None.
    """
    get_database = getattr(mongo_client, "get_database", None)
    if get_database is None:
        raise ValueError("MongoDB client does not have a get_database method")
    database = get_database("test_db")
    # Patch list_collection_names on the underlying mongomock database
    # to accept authorizedCollections and nameOnly kwargs that newer
    # pymongo/Beanie versions pass but mongomock does not support.
    orig_list_collection_names = database.delegate.list_collection_names

    def _patched_list_collection_names(
        filter: dict | None = None,  # noqa: A002
        session: object | None = None,
        **kwargs: object,
    ) -> list[str]:
        return orig_list_collection_names(filter=filter, session=session)

    database.delegate.list_collection_names = _patched_list_collection_names
    await init_beanie(
        database=database,
        document_models=basic.get_all_subclasses(base_mongo_models.BaseEntity),
    )


@pytest_asyncio.fixture(scope="session")
async def db(mongo_client: object) -> AsyncGenerator[None]:
    """
    Fixture to provide a database for testing.

    Args:
        mongo_client: AsyncMongoMockClient.

    Returns:
        None.
    """
    Settings.config_logger()
    logging.info("Initializing database")
    await init_db(mongo_client)
    logging.info("Database initialized")
    yield
    logging.info("Cleaning up database")


@pytest_asyncio.fixture(scope="session")
async def client(db: None) -> AsyncGenerator[httpx.AsyncClient]:
    """
    Fixture to provide an AsyncClient for FastAPI app.

    Args:
        db: Ensures the test database is initialized before requests.

    Returns:
        AsyncClient.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://test.usso.io",
    ) as ac:
        yield ac
