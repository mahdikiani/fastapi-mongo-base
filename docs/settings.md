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
- `SHUTDOWN_TIMEOUT`: Max seconds to drain in-flight HTTP requests on SIGTERM (default `20`)
- `BACKGROUND_SHUTDOWN_TIMEOUT`: Max seconds to wait for the worker and `spawn()`ed tasks before cancelling them (default `10`)
- `SHUTDOWN_FORCE_EXIT_AFTER`: Seconds after SIGTERM before a watchdog dumps all thread stacks and exits with code 1 (default: the budget above + 5, i.e. 35s for `serve()`, 15s for `run_worker_process()`; `0` disables)

## Example .env

```
MONGO_URI=mongodb://localhost:27017/db
APP_ENV=development
BASE_PATH=/api/v1
```

For a full list of settings, see the `Settings` class in your `config.py` file. 