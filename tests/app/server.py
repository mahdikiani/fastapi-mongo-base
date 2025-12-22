"""Test server for the FastAPI MongoDB base package."""

import dataclasses
from decimal import Decimal
from pathlib import Path

from pydantic import field_validator

from src.fastapi_mongo_base.core import app_factory, config
from src.fastapi_mongo_base.models import BaseEntity
from src.fastapi_mongo_base.routes import AbstractBaseRouter
from src.fastapi_mongo_base.schemas import BaseEntitySchema
from src.fastapi_mongo_base.utils import bsontools


class TestEntitySchema(BaseEntitySchema):
    """
    Test entity schema for the test server.

    Args:
        name: Name of the entity.
        number: Number of the entity.
    """

    name: str
    number: Decimal = Decimal(8)

    @field_validator("number", mode="before")
    @classmethod
    def validate_number(cls, v: object) -> Decimal:
        """
        Validate the number of the entity.

        Args:
            v: Value to validate.

        Returns:
            Decimal value.
        """
        return bsontools.decimal_amount(v)


class TestEntity(TestEntitySchema, BaseEntity):
    """
    Test entity for the test server.

    Args:
        TestEntitySchema: Test entity schema.
        BaseEntity: Base entity.
    """

    pass


class TestRouter(AbstractBaseRouter):
    """
    Test router for the test server.

    Args:
        prefix: Prefix of the router.
    """

    model = TestEntity
    schema = TestEntitySchema

    def __init__(self) -> None:
        """
        Initialize the test router.

        Args:
            prefix: Prefix of the router.
        """
        super().__init__(prefix="/test")


@dataclasses.dataclass
class Settings(config.Settings):
    """
    Settings for the test server.

    Args:
        project_name: Name of the project.
        base_dir: Directory of the project.
        base_path: Base path of the project.
        mongo_uri: URI of the MongoDB database.
    """

    project_name: str = "test"
    base_dir: Path = Path(__file__).parent
    base_path: str = ""
    mongo_uri: str = "mongodb://!!localhost:27017"


app = app_factory.create_app(settings=Settings())
app.include_router(TestRouter().router)
