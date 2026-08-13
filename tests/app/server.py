"""Test server for the FastAPI MongoDB base package."""

import dataclasses
from decimal import Decimal
from pathlib import Path
from typing import ClassVar

from pydantic import field_validator

from fastapi_mongo_base.core import app_factory, config
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.routes import AbstractBaseRouter
from fastapi_mongo_base.schemas import BaseEntitySchema
from fastapi_mongo_base.utils import bsontools


class TestEntitySchema(BaseEntitySchema):
    """
    Test entity schema for the test server.

    Args:
        name: Name of the entity.
        number: Number of the entity.

    """

    # pytest collects ``Test*`` classes; this is an app model.
    __test__: ClassVar[bool] = False

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
        amount = bsontools.decimal_amount(v)
        if amount is None:
            raise ValueError("number is required")
        return amount


class TestEntity(TestEntitySchema, BaseEntity):
    """
    Test entity for the test server.

    Args:
        TestEntitySchema: Test entity schema.
        BaseEntity: Base entity.

    """

    __test__: ClassVar[bool] = False


class TestRouter(AbstractBaseRouter):
    """
    Test router for the test server.

    Args:
        prefix: Prefix of the router.

    """

    __test__ = False
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
