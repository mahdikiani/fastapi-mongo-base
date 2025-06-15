# Usage

Basic usage examples for fastapi-mongo-base.

---

## 2. Define Schemas and Models

**schemas.py**
```python
from fastapi_mongo_base.schemas import BaseEntitySchema

class BookSchema(BaseEntitySchema):
    title: str
    author: str
    publish_year: int
    isbn: str | None = None
```

**models.py**
```python
from fastapi_mongo_base.models import BaseEntity
from .schemas import BookSchema

class Book(BookSchema, BaseEntity):
    """Book model that inherits from both BookSchema and BaseEntity"""
    pass
```

---

## 3. Create and Register Routers

**routes.py**
```python
from fastapi_mongo_base.routes import AbstractBaseRouter
from . import models, schemas

class BookRouter(AbstractBaseRouter):
    model = models.Book
    schema = schemas.BookSchema

router = BookRouter().router
```

**server/server.py**
```python
from fastapi import FastAPI
from apps.books.routes import router as book_router
from .config import Settings

app = FastAPI()
app.include_router(book_router, prefix=f"{Settings().base_path}/books")
```

---

## 4. MongoDB Configuration

Set your MongoDB URI in `.env` or as an environment variable:

```.env
MONGO_URI=mongodb://localhost:27017/db
```

- For Docker, use `mongo` as the hostname:  

```
MONGO_URI=mongodb://mongo:27017/db
```

---

## 5. Running the Application

- **Locally**:
```bash
pip install fastapi-mongo-base uvicorn

docker run -d -p 27017:27017 --name mongo mongo

uvicorn app.main:app --reload
```

- **With Docker Compose**:  
  See [Quick Start](quickstart.md) for a full example.

---

## 6. Custom Endpoints

You can add custom endpoints for advanced queries or background tasks.  
See [Endpoints & Customization](endpoints.md) for details.

---

## 7. More Resources

- [Quick Start](quickstart.md)
- [Tutorial](tutorial.md)
- [Boilerplate Project](boilerplate.md)

---
