# FastAPI MongoDB Base

A powerful boilerplate application for building FastAPI applications with MongoDB integration. This package provides a solid foundation with pre-configured models, schemas, and abstract routers to help you start your development project quickly.

## Features

- 🚀 **FastAPI Integration**: Built on top of FastAPI for high performance and easy-to-use API development
- 📦 **MongoDB Support**: Seamless integration with MongoDB using Beanie ODM
- 🔒 **Authentication Ready**: Built-in JWT authentication support
- 📝 **Pydantic Models**: Type-safe data validation and serialization
- 🎯 **Abstract Routers**: Pre-built abstract CRUD operations
- 🔄 **Caching Support**: Built-in caching mechanism for improved performance
- 🛠 **Task Management**: Background task handling capabilities
- 📸 **Image Processing**: Optional image processing support (requires Pillow)

## Installation

```bash
pip install fastapi-mongo-base
```

For image processing support:
```bash
pip install "fastapi-mongo-base[image]"
```

For development/testing:
```bash
pip install "fastapi-mongo-base[test]"
```

## Quick Start

1. Create a new FastAPI application:

```python
from fastapi import FastAPI
from fastapi_mongo_base import MongoBase

app = FastAPI()
mongo_base = MongoBase(app)

# Configure MongoDB connection
mongo_base.setup_mongodb(
    mongodb_url="mongodb://localhost:27017",
    database_name="your_database"
)
```

2. Create a model:

```python
from fastapi_mongo_base.models import BaseModel

class User(BaseModel):
    name: str
    email: str
```

3. Create a router:

```python
from fastapi_mongo_base.routes import BaseRouter

user_router = BaseRouter(User)
app.include_router(user_router, prefix="/users", tags=["users"])
```

## Requirements

- Python >= 3.9
- FastAPI >= 0.65.0
- Pydantic >= 2.0.0
- MongoDB
- Other dependencies as specified in pyproject.toml

## Project Structure

```
fastapi_mongo_base/
├── core/           # Core functionality and configurations
├── models.py       # Base models and database schemas
├── routes.py       # Abstract routers and endpoints
├── schemas.py      # Pydantic models for request/response
├── tasks.py        # Background task handling
├── cached.py       # Caching utilities
└── utils/          # Utility functions and helpers
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

Distributed under the MIT License. See [LICENSE](LICENSE.txt) for more information.

## Author

- Mahdi Kiani - [GitHub](https://github.com/mahdikiani)

## Acknowledgments

- FastAPI team for the amazing framework
- MongoDB team for the powerful database
- All contributors who have helped shape this project
