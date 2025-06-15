# Endpoints & Customization

## Controlling Endpoints

You can enable, disable, or customize endpoints by subclassing `AbstractBaseRouter` and overriding its methods.

### Example: Disable Delete Endpoint
```python
from fastapi_mongo_base.routes import AbstractBaseRouter

class MyRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(model=MyModel)
    
    def config_routes(self, **kwargs):
        super().config_routes(delete_route=False)
        
    async def get_summary(self, uid: str):
        item = await self.get_item(uid)
        return item.get_summary()
```


### Example: Add custom summary endpoint
```python
from fastapi_mongo_base.routes import AbstractBaseRouter

class MyRouter(AbstractBaseRouter):
    def __init__(self):
        super().__init__(model=MyModel)
    
    def config_routes(self, **kwargs):
        super().config_routes()
        self.router.add_api_route(
            path="/{uid}/summary",
            endpoint=self.summary,
            methods=["GET"],
            status_code=201,
        )

    async def get_summary(self, uid: str):
        item = await self.get_item(uid)
        return item.get_summary()
```


## Adding Custom Endpoints

You can add custom endpoints for complex queries or task processing:

```python
from fastapi import APIRouter, Depends
from .models import MyModel

router = APIRouter()

@router.get("/custom-search")
def custom_search(query: str):
    # Implement complex query logic here
    return MyModel.find_custom(query)
```

## Task Processing Example

For background tasks, use FastAPI's `BackgroundTasks`:

```python
from fastapi import BackgroundTasks

@router.post("/process-task")
def process_task(data: dict, background_tasks: BackgroundTasks):
    background_tasks.add_task(long_running_task, data)
    return {"status": "processing"}
```

See the [Tutorial](tutorial.md) for a full walkthrough. 