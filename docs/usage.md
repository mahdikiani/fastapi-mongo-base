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

### Graceful shutdown

Run the app with `serve()` so a deploy or restart does not cut in-flight work:

```python
# main.py
from fastapi_mongo_base.core.lifecycle import serve
from server.server import app

if __name__ == "__main__":
    serve("main:app", host="0.0.0.0")
```

On SIGTERM/SIGINT:

1. `/ready` returns 503 and the stop event is set, so workers start winding down.
2. uvicorn stops accepting connections and waits up to `SHUTDOWN_TIMEOUT` for in-flight requests.
3. The lifespan waits up to `BACKGROUND_SHUTDOWN_TIMEOUT` for the worker and for tasks started with `spawn()`, then cancels what is left (logged by task name).
4. `shutdown_functions` run in reverse order, then Mongo/Redis/SQL close.

Workers can never keep the process alive:

- A cancelled task gets 3 seconds to finish cancelling. A task that swallows `CancelledError` is logged with its stack and abandoned.
- A watchdog thread forces the exit if shutdown overruns `SHUTDOWN_FORCE_EXIT_AFTER` (default 35s for `serve()`, 15s for workers). This also covers a worker that blocks the event loop with sync code. It logs `Shutdown did not finish ... forcing exit`, dumps every thread's stack to stderr (showing where the code is stuck), and exits with code 1.

Make background work shutdown-aware:

```python
import asyncio

from fastapi_mongo_base.core import app_factory
from fastapi_mongo_base.core.lifecycle import spawn


async def worker(stop: asyncio.Event) -> None:
    # A worker that takes a parameter receives the stop event and is awaited.
    # A zero-argument worker is cancelled immediately (previous behavior).
    while not stop.is_set():
        await process_due_jobs()
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass


async def upload_file(data: bytes) -> None:
    # Instead of asyncio.create_task: shutdown waits for this task.
    spawn(store(data), name="upload")


app = app_factory.create_app(
    settings=Settings(),
    worker=worker,
    shutdown_functions=[telegram_client.disconnect],
)
```

For non-HTTP worker processes, use `run_worker_process(main)`; `main` receives the stop event. For apscheduler, `await run_apscheduler(scheduler, stop)` (extra `scheduler`) lets running jobs finish instead of cancelling them.

Set the container grace period above `SHUTDOWN_FORCE_EXIT_AFTER` (e.g. `stop_grace_period: 40s` for the 35s default), so the watchdog's stack dump happens before SIGKILL, and in Kubernetes add a short `preStop` sleep so the pod leaves the endpoints before SIGTERM.

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
