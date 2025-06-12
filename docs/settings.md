# Settings

The `Settings` class manages configuration for your FastAPI app, including MongoDB connection and other environment variables.

## Example

```python
from fastapi_mongo_base.core.config import Settings
settings = Settings()
print(settings.mongo_uri)
```

## Common Environment Variables

- `MONGO_URI`: MongoDB connection string (e.g., `mongodb://localhost:27017/db`)
- `APP_ENV`: Application environment (e.g., `development`, `production`)
- `BASE_PATH`: API base path (e.g., `/api/v1`)

## Example .env

```
MONGO_URI=mongodb://localhost:27017/db
APP_ENV=development
BASE_PATH=/api/v1
```

For a full list of settings, see the `Settings` class in your `config.py` file. 