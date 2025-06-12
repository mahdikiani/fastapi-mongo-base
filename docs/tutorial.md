# Tutorial: Building a Books Module

This tutorial walks you through creating a complete Books module using fastapi-mongo-base.

## 1. Create the Module Directory
```bash
mkdir -p app/apps/books
cd app/apps/books
touch __init__.py models.py schemas.py routes.py services.py
```

## 2. Define Schemas
```python
# schemas.py
from fastapi_mongo_base.schemas import BaseEntitySchema

class BookSchema(BaseEntitySchema):
    title: str
    author: str
    publish_year: int
    isbn: str | None = None
```

## 3. Create the Model
```python
# models.py
from fastapi_mongo_base.models import BaseEntity
from .schemas import BookSchema

class Book(BookSchema, BaseEntity):
    """Book model that inherits from both BookSchema and BaseEntity"""
    pass
```

## 4. Set Up Routes
```python
# routes.py
from fastapi_mongo_base.routes import AbstractBaseRouter
from . import models, schemas

class BookRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(model=models.Book, schema=schemas.BookSchema)

router = BookRouter().router
```

## 5. Register the Router
```python
# server/server.py
from fastapi_mongo_base.core import app_factory
from apps.books import router as book_router
from . import config

app = app_factory.create_app(settings=config.Settings())
app.include_router(book_router, prefix=f"{config.Settings.base_path}/books")
```

## 6. Run the Project
- With Docker Compose:
  ```bash
  docker compose up --build -d
  ```
- Or locally:
  ```bash
  uvicorn app.main:app --reload
  ```

## 7. Access the API
- Swagger UI: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- ReDoc: [http://localhost:8000/api/v1/redoc](http://localhost:8000/api/v1/redoc) 