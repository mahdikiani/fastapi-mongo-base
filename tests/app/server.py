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
    name: str
    number: Decimal = Decimal(8)

    @field_validator("number", mode="before")
    def validate_number(cls, v):
        return bsontools.decimal_amount(v)


class TestEntity(TestEntitySchema, BaseEntity):
    pass


class TestRouter(AbstractBaseRouter):
    model = TestEntity
    schema = TestEntitySchema

    def __init__(self):
        super().__init__(prefix="/test")


@dataclasses.dataclass
class Settings(config.Settings):
    project_name: str = "test"
    base_dir: Path = Path(__file__).parent
    base_path: str = ""
    mongo_uri: str = "mongodb://!!localhost:27017"


app = app_factory.create_app(settings=Settings())
app.include_router(TestRouter().router)
