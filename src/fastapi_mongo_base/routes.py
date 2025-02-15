import asyncio
import uuid
from datetime import datetime
from typing import Any, Generic, Type, TypeVar

import singleton
from fastapi import APIRouter, BackgroundTasks, Query, Request

try:
    from core.exceptions import BaseHTTPException
except ImportError:
    from .core.exceptions import BaseHTTPException

try:
    from server.config import Settings
except ImportError:
    from .core.config import Settings

from .handlers import create_dto
from .models import BaseEntity, BaseEntityTaskMixin
from .schemas import BaseEntitySchema, PaginatedResponse
from .tasks import TaskStatusEnum

# Define a type variable
T = TypeVar("T", bound=BaseEntity)
TE = TypeVar("TE", bound=BaseEntityTaskMixin)
TS = TypeVar("TS", bound=BaseEntitySchema)


class AbstractBaseRouter(Generic[T, TS], metaclass=singleton.Singleton):

    def __init__(
        self,
        model: Type[T],
        user_dependency: Any,
        *args,
        prefix: str = None,
        tags: list[str] = None,
        schema: Type[TS] = None,
        **kwargs,
    ):
        self.model = model
        if schema is None:
            schema = self.model
        self.schema = schema
        self.user_dependency = user_dependency
        if prefix is None:
            prefix = f"/{self.model.__name__.lower()}s"
        if tags is None:
            tags = [self.model.__name__]
        self.router = APIRouter(prefix=prefix, tags=tags, **kwargs)

        self.config_schemas(self.schema, **kwargs)
        self.config_routes(**kwargs)

    def config_schemas(self, schema, **kwargs):
        self.schema = schema
        self.list_item_schema = kwargs.get("list_item_schema", schema)
        self.list_response_schema = kwargs.get(
            "list_response_schema", PaginatedResponse[self.list_item_schema]
        )
        self.retrieve_response_schema = kwargs.get("retrieve_response_schema", schema)
        self.create_response_schema = kwargs.get("create_response_schema", schema)
        self.update_response_schema = kwargs.get("update_response_schema", schema)
        self.delete_response_schema = kwargs.get("delete_response_schema", schema)

        self.create_request_schema = kwargs.get("create_request_schema", schema)
        self.update_request_schema = kwargs.get("update_request_schema", schema)

    def config_routes(self, **kwargs):
        prefix: str = kwargs.get("prefix", "")
        prefix = prefix.strip("/")
        prefix = f"/{prefix}" if prefix else ""

        if kwargs.get("list_route", True):
            self.router.add_api_route(
                f"{prefix}/",
                self.list_items,
                methods=["GET"],
                response_model=self.list_response_schema,
                status_code=200,
            )

        if kwargs.get("retrieve_route", True):
            self.router.add_api_route(
                f"{prefix}/{{uid:uuid}}",
                self.retrieve_item,
                methods=["GET"],
                response_model=self.retrieve_response_schema,
                status_code=200,
            )

        if kwargs.get("create_route", True):
            self.router.add_api_route(
                f"{prefix}/",
                self.create_item,
                methods=["POST"],
                response_model=self.create_response_schema,
                status_code=201,
            )

        if kwargs.get("update_route", True):
            self.router.add_api_route(
                f"{prefix}/{{uid:uuid}}",
                self.update_item,
                methods=["PATCH"],
                response_model=self.update_response_schema,
                status_code=200,
            )

        if kwargs.get("delete_route", True):
            self.router.add_api_route(
                f"{prefix}/{{uid:uuid}}",
                self.delete_item,
                methods=["DELETE"],
                response_model=self.delete_response_schema,
                # status_code=204,
            )

        if kwargs.get("statistics_route", True):
            self.router.add_api_route(
                f"{prefix}/statistics",
                self.statistics,
                methods=["GET"],
            )

    async def get_item(
        self,
        uid: uuid.UUID,
        user_id: uuid.UUID = None,
        business_name: str = None,
        **kwargs,
    ):
        item = await self.model.get_item(
            uid, user_id=user_id, business_name=business_name, **kwargs
        )
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        return item

    async def get_user(self, request: Request, *args, **kwargs):
        if self.user_dependency is None:
            return None
        if asyncio.iscoroutinefunction(self.user_dependency):
            return await self.user_dependency(request)
        return self.user_dependency(request)

    async def get_user_id(self, request: Request, *args, **kwargs):
        user = await self.get_user(request)
        user_id = user.uid if user else None
        return user_id

    async def statistics(
        self,
        request: Request,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
    ):
        return {
            "total": await self.model.total_count(**request.query_params),
            **request.query_params,
        }

    async def _list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        **kwargs,
    ):
        user_id = kwargs.pop("user_id", await self.get_user_id(request))
        limit = max(1, min(limit, Settings.page_max_limit))

        items, total = await self.model.list_total_combined(
            user_id=user_id,
            offset=offset,
            limit=limit,
            **kwargs,
        )
        items_in_schema = [self.list_item_schema(**item.model_dump()) for item in items]

        return PaginatedResponse(
            items=items_in_schema,
            total=total,
            offset=offset,
            limit=limit,
        )

    async def list_items(
        self,
        request: Request,
        offset: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=Settings.page_max_limit),
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
    ):
        return await self._list_items(
            request=request,
            offset=offset,
            limit=limit,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )

    async def retrieve_item(
        self,
        request: Request,
        uid: uuid.UUID,
    ):
        user_id = await self.get_user_id(request)
        item = await self.get_item(uid, user_id=user_id)
        return item

    async def create_item(
        self,
        request: Request,
        data: dict,
    ):
        user_id = await self.get_user_id(request)
        item_data: TS = await create_dto(self.create_response_schema)(
            request, user_id=user_id
        )
        item = await self.model.create_item(item_data.model_dump())
        # item: T = await create_dto(self.create_request_schema)(request, user)
        await item.save()
        return item

    async def update_item(
        self,
        request: Request,
        uid: uuid.UUID,
        data: dict,
    ):
        user_id = await self.get_user_id(request)
        item = await self.get_item(uid, user_id=user_id)
        # item = await update_dto(self.model)(request, user)
        item = await self.model.update_item(item, data)
        return item

    async def delete_item(
        self,
        request: Request,
        uid: uuid.UUID,
    ):
        user_id = await self.get_user_id(request)
        item = await self.get_item(uid, user_id=user_id)

        item = await self.model.delete_item(item)
        return item


class AbstractTaskRouter(AbstractBaseRouter[TE, TS]):
    def __init__(
        self,
        model: Type[TE],
        user_dependency: Any,
        schema: TS,
        draftable: bool = True,
        *args,
        **kwargs,
    ):
        super().__init__(model, user_dependency, schema=schema, *args, **kwargs)
        self.draftable = draftable

    def config_routes(self, **kwargs):
        super().config_routes(**kwargs)

        if kwargs.get("start_route", True):
            self.router.add_api_route(
                "/{uid:uuid}/start",
                self.start_item,
                methods=["POST"],
                response_model=self.retrieve_response_schema,
            )

        if kwargs.get("webhook_route", True):
            self.router.add_api_route(
                "/{uid:uuid}/webhook",
                self.webhook,
                methods=["POST"],
                status_code=200,
            )

    async def statistics(
        self,
        request: Request,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        task_status: TaskStatusEnum | None = None,
    ):
        return await super().statistics(request)

    async def create_item(
        self, request: Request, data: dict, background_tasks: BackgroundTasks
    ):
        if not self.draftable:
            data["task_status"] = "init"

        item: TE = await super().create_item(request, data)

        if item.task_status == "init" or not self.draftable:
            background_tasks.add_task(item.start_processing)
        return item

    async def start_item(
        self, request: Request, uid: uuid.UUID, background_tasks: BackgroundTasks
    ):
        user_id = await self.get_user_id(request)
        item: TE = await self.get_item(uid, user_id=user_id)
        background_tasks.add_task(item.start_processing)
        return item.model_dump()

    async def webhook(
        self,
        request: Request,
        uid: uuid.UUID,
        data: dict,
    ):
        import logging

        logging.info(f"Webhook received for {uid} with data {data}")
        return {"message": f"Webhook received for {uid} with data", **data}


def copy_router(router: APIRouter, new_prefix: str):
    new_router = APIRouter(prefix=new_prefix)
    for route in router.routes:
        new_router.add_api_route(
            route.path.replace(router.prefix, ""),
            route.endpoint,
            methods=[
                method
                for method in route.methods
                if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]
            ],
            name=route.name,
            response_class=route.response_class,
            status_code=route.status_code,
            tags=route.tags,
            dependencies=route.dependencies,
            summary=route.summary,
            description=route.description,
            response_description=route.response_description,
            responses=route.responses,
            deprecated=route.deprecated,
            include_in_schema=route.include_in_schema,
            response_model=route.response_model,
            response_model_include=route.response_model_include,
            response_model_exclude=route.response_model_exclude,
            response_model_by_alias=route.response_model_by_alias,
        )

    return new_router
