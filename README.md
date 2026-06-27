# FastAPI MongoDB Base

A powerful package that provides base classes and utilities for building FastAPI applications with MongoDB. Built on top of FastAPI and Beanie ODM, it offers pre-built CRUD operations, authentication, caching, and more.

## ✨ Features

- 🚀 **Ready-to-use CRUD Operations**: Pre-built abstract routers with full CRUD functionality
- 📦 **MongoDB Integration**: Seamless integration using Beanie ODM
- 🔒 **Authentication**: Built-in JWT authentication support
- 📝 **Type Safety**: Pydantic models for request/response validation
- 🔄 **Caching**: Built-in caching mechanism for improved performance
- 🛠 **Background Tasks**: Easy background task handling
- 📸 **Image Processing**: Optional image processing support (requires Pillow)

## 📦 Installation

```bash
pip install fastapi-mongo-base
```

## 📄 Documentation

The complete documentation is available at: [https://mahdikiani.github.io/fastapi-mongo-base/](https://mahdikiani.github.io/fastapi-mongo-base/)

You can also ask questions about the project using DeepWiki:

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/mahdikiani/fastapi-mongo-base)


## 🚀 Quick Start

1. Create your schema:
```python
from fastapi_mongo_base.schemas import BaseEntitySchema

class UserSchema(BaseEntitySchema):
    email: str
    name: str
    age: int | None = None
```

2. Create your model:
```python
from fastapi_mongo_base.models import BaseEntity
from .schemas import UserSchema

class User(UserSchema, BaseEntity):
    """User model that inherits from both UserSchema and BaseEntity"""
    pass
```

3. Set up your router:
```python
from fastapi_mongo_base.routes import AbstractBaseRouter
from . import models, schemas

class UserRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(model=models.User, schema=schemas.UserSchema)

router = UserRouter().router
```

4. Include in your FastAPI app:
```python
from fastapi import FastAPI
from fastapi_mongo_base.core import app_factory

app = app_factory.create_app()
app.include_router(router, prefix="/api/v1/users")
```

## 📚 Available Endpoints

Each router automatically provides these endpoints:

- `GET /api/v1/users` - List all users
- `POST /api/v1/users` - Create a new user
- `GET /api/v1/users/{id}` - Get a specific user
- `PATCH /api/v1/users/{id}` - Update a user
- `DELETE /api/v1/users/{id}` - Delete a user

## 🔧 Configuration

Configure your application using environment variables or a settings class:

```python
import dataclasses
import logging
import logging.config
import os

import dotenv
from singleton import Singleton

dotenv.load_dotenv()


@dataclasses.dataclass
class Settings(metaclass=Singleton):
    root_url: str = os.getenv("DOMAIN", default="http://localhost:8000")
    project_name: str = os.getenv("PROJECT_NAME", default="PROJECT")
    base_path: str = "/api/v1"
    worker_update_time: int = int(os.getenv("WORKER_UPDATE_TIME", default=180))
    testing: bool = os.getenv("DEBUG", default=False)

    page_max_limit: int = 100

    mongo_uri: str = os.getenv("MONGO_URI", default="mongodb://localhost:27017/")
    redis_uri: str = os.getenv("REDIS_URI", default="redis://localhost:6379/0")

    app_id: str = os.getenv("APP_ID")
    app_secret: str = os.getenv("APP_SECRET")

    JWT_CONFIG: str = os.getenv(
        "USSO_JWT_CONFIG",
        default='{"jwk_url": "https://sso.usso.io/website/jwks.json","type": "RS256","header": {"type": "Cookie", "name": "usso-access-token"} }',
    )

    @classmethod
    def get_coverage_dir(cls):
        return cls.base_dir / "htmlcov"

    @classmethod
    def get_log_config(
        cls, console_level: str = "INFO", file_level: str = "INFO", **kwargs
    ):
        log_config = {
            "formatters": {
                "standard": {
                    "format": "[{levelname} : {filename}:{lineno} : {asctime} -> {funcName:10}] {message}",
                    "style": "{",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": console_level,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "level": file_level,
                    "filename": cls.base_dir / "logs" / "app.log",
                    "formatter": "standard",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": "INFO",
                    "propagate": True,
                },
                "httpx": {
                    "handlers": ["console", "file"],
                    "level": "WARNING",
                    "propagate": False,
                },
            },
            "version": 1,
        }
        return log_config

    @classmethod
    def config_logger(cls):
        log_config = cls.get_log_config()
        if log_config["handlers"].get("file"):
            (cls.base_dir / "logs").mkdir(parents=True, exist_ok=True)

        logging.config.dictConfig(cls.get_log_config())

```

## 🛠️ Advanced Usage

### HTTP Exceptions

The package provides structured, bilingual HTTP errors (`en` / `fa`) with a consistent JSON shape. Exception handlers are registered automatically when you create the app via `app_factory.create_app()` (or call `setup_exception_handlers` manually).

#### Response format

Every handled error returns JSON like:

```json
{
  "message": {
    "en": "User with id 'abc123' not found",
    "fa": "User با شناسه «abc123» پیدا نشد."
  },
  "error": "item_not_found",
  "detail": "User با شناسه «abc123» پیدا نشد.",
  "uid": "abc123"
}
```

- `message` — full bilingual map (always included when available).
- `error` — stable machine-readable error code.
- `detail` — user-facing text; follows the `Accept-Language` header (`fa` or `en`) unless you pass an explicit `detail`.
- Extra keyword arguments (e.g. `uid`, `resource`) are merged into the response body.

#### Using predefined exceptions

**Resource errors** — for API entities and business resources:

```python
from fastapi_mongo_base.core.errors.resource_errors import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
    ResourceForbiddenError,
    ResourceConflictError,
)

async def get_user(uid: str):
    user = await User.get(uid)
    if user is None:
        raise ResourceNotFoundError(resource="User", uid=uid)
    return user
```

| Class | HTTP status | `error` code |
|-------|-------------|--------------|
| `ResourceNotFoundError` | 404 | `item_not_found` |
| `ResourceAlreadyExistsError` | 409 | `resource_already_exists` |
| `ResourcePaymentRequiredError` | 402 | `payment_required` |
| `ResourceForbiddenError` | 403 | `forbidden` |
| `ResourceConflictError` | 409 | `resource_conflict` |
| `ResourceGoneError` | 410 | `resource_gone` |
| `ResourceLockedError` | 423 | `resource_locked` |

**MongoDB errors** — for database-layer failures (also mapped automatically from PyMongo driver errors):

```python
from fastapi_mongo_base.core.errors.db_errors import (
    DocumentNotFoundError,
    DuplicateKeyError,
    InvalidObjectIdError,
)

async def get_document(collection: str, uid: str):
    doc = await find_one(collection, uid)
    if doc is None:
        raise DocumentNotFoundError(collection=collection, uid=uid)
    return doc
```

Common classes include `MongoDBConnectionError`, `DocumentNotFoundError`, `DocumentAlreadyExistsError`, `DuplicateKeyError`, `InvalidObjectIdError`, `DocumentValidationError`, and `WriteConflictError`. See `fastapi_mongo_base.core.errors.db_errors` for the full list.

Predefined exceptions accept optional context kwargs (`resource`, `uid`, `collection`, etc.) that both enrich the message and appear in the response payload.

#### Defining custom exceptions

Subclass a predefined exception and override class attributes. **No custom `__init__` or i18n logic is required** — `BaseHTTPException` resolves `status_code`, `error_code`, and default messages from class attributes automatically:

```python
from fastapi_mongo_base.core.errors.resource_errors import ResourceNotFoundError

class OrderNotFoundError(ResourceNotFoundError):
    default_message = "Order not found"
    default_message_fa = "سفارش پیدا نشد."  # optional; inherits parent fa if omitted

# Uses status_code=404, error="item_not_found", and your messages
raise OrderNotFoundError()

# Context-aware messages still work from the parent class
raise OrderNotFoundError(resource="Order", uid="ord_123")
```

Override only what you need:

```python
from fastapi_mongo_base.core.errors.db_errors import MongoDBConnectionTimeoutError

class AppDatabaseTimeoutError(MongoDBConnectionTimeoutError):
    default_message = "The app database is temporarily unavailable"
    # status_code (503) and error_code inherit from the parent chain
```

`ResourceError` and `MongoDBError` themselves are also class-attribute based (no extra constructor needed) unless you want context-specific dynamic messages.

Class attributes used by the framework:

| Attribute | Purpose |
|-----------|---------|
| `status_code` | HTTP status code |
| `error_code` | Value of the `error` field in JSON |
| `default_message` | English text (`message.en`) |
| `default_message_fa` | Persian text (`message.fa`); walks up the parent chain when omitted |

#### Overrides at raise time

You can override messages or detail when raising:

```python
raise ResourceNotFoundError(
    resource="User",
    uid=uid,
    detail="This user was removed by an admin.",  # explicit detail wins
)

raise ResourceNotFoundError(
    message={"en": "Custom EN", "fa": "متن سفارشی"},
)
```

Or use the helper for consistency:

```python
from fastapi_mongo_base.core.exceptions import map_exception_message

raise ResourceNotFoundError(
    message=map_exception_message("Custom EN", "متن سفارشی"),
)
```

#### Legacy error catalog

For ad-hoc errors without a dedicated class, register messages in the global catalog and raise `BaseHTTPException`:

```python
from fastapi_mongo_base.core.exceptions import BaseHTTPException, error_messages

error_messages["invalid_coupon"] = {
    "en": "This coupon is not valid",
    "fa": "این کد تخفیف معتبر نیست",
}

raise BaseHTTPException(status_code=400, error="invalid_coupon")
```

#### Client locale

Send `Accept-Language: fa` (or `fa-IR`) to receive Persian in `detail`; omit the header or send `en` for English. The full `message` map is always returned in both languages when available.

### Custom Business Logic

Extend the base router to add custom endpoints:

```python
from fastapi_mongo_base.routes import AbstractBaseRouter

class UserRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(model=models.User, schema=schemas.UserSchema)
    
    @router.get("/me")
    async def get_current_user(self):
        # Your custom logic here
        pass
```

### Background Tasks

Handle background tasks easily:

```python
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from server.config import Settings

logging.getLogger("apscheduler").setLevel(logging.WARNING)

async def log_something():
    logging.info('something')

async def worker():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        log_something, "interval", seconds=Settings.worker_update_time
    )

    scheduler.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
```

## 📋 Requirements

- Python >= 3.9
- FastAPI >= 0.65.0
- Pydantic >= 2.0.0
- MongoDB
- Beanie ODM

## 🔍 Project Structure

```
fastapi_mongo_base/
├── core/           # Core functionality and configurations
├── models.py       # Base models and database schemas
├── routes.py       # Abstract routers and endpoints
├── schemas.py      # Pydantic models for request/response
├── tasks.py        # Background task handling
└── utils/          # Utility functions and helpers
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License

Distributed under the MIT License. See [LICENSE](LICENSE.txt) for more information.

## 👤 Author

- Mahdi Kiani - [GitHub](https://github.com/mahdikiani)

## 🙏 Acknowledgments

- FastAPI team for the amazing framework
- MongoDB team for the powerful database
- Beanie team for the excellent ODM
- All contributors who have helped shape this project
