# Quick Start

Get up and running with **fastapi-mongo-base** in minutes!

## Minimal Example

```python
# app/main.py
from fastapi_mongo_base.core import config, app_factory
from fastapi_mongo_base.models import BaseEntity
from fastapi_mongo_base.routes import AbstractBaseRouter
from fastapi_mongo_base.schemas import BaseEntitySchema

class ItemSchema(BaseEntity):
    name: str
    description: str | None = None

class Item(BaseEntity):
    name: str
    description: str | None = None

class ItemRouter(AbstractBaseRouter):
    model = Item
    schema = ItemSchema



@dataclasses.dataclass
class Settings(config.Settings):
    project_name: str = "sample fastapi mongo base project"
    base_dir: Path = Path(__file__).parent
    base_path: str = ""
    mongo_uri: str = "mongodb://localhost:27017"


app = app_factory.create_app(settings=Settings())
app.include_router(TestRouter().router)

```

## Running Locally

1. **Install dependencies:**
```bash
pip install fastapi-mongo-base uvicorn
```
2. **Start MongoDB** (locally or with Docker):
```bash
docker run -d -p 27017:27017 --name mongo mongo
```
3. **Run your app:**
```bash
uvicorn app.main:app --reload
```

## Running with Docker Compose

1. Copy the [docker-compose.yml](https://github.com/mahdikiani/FastAPIMongoLaunchpad/blob/main/docker-compose.yml) from the boilerplate or create your own:
```yaml
services:
    mongo:
        image: mongo:latest
        ports:
            - 27017:27017
    app:
        build: .
        ports:
            - 8000:8000
        environment:
            - MONGO_URI=mongodb://mongo:27017/db
        depends_on:
            - mongo
```
2. **Start everything:**
```bash
docker compose up --build -d
```

3. **See Logs**
```bash
docker compose logs -f app
```


Your API will be available at [http://localhost:8000/docs](http://localhost:8000/docs) 