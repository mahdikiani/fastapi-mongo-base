import dataclasses
from pathlib import Path

from src.fastapi_mongo_base.core import app_factory, config
from src.fastapi_mongo_base.models import BaseEntity
from src.fastapi_mongo_base.routes import AbstractBaseRouter
from src.fastapi_mongo_base.schemas import BaseEntitySchema


class TestEntitySchema(BaseEntitySchema):
    name: str


class TestEntity(TestEntitySchema, BaseEntity):
    pass


class TestRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(
            schema=TestEntitySchema,
            model=TestEntity,
            prefix="/test"
        )


@dataclasses.dataclass
class Settings(config.Settings):
    project_name: str = "test"
    base_dir: Path = Path(__file__).parent
    base_path: str = ""


app = app_factory.create_app(settings=Settings())
app.include_router(TestRouter().router)
