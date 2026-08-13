"""Abstract routers for CRUD operations with FastAPI."""

import inspect
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

import singleton
from fastapi import APIRouter, BackgroundTasks, Query, Request
from pydantic import BaseModel

from .core.config import Settings
from .errors.base import BaseHTTPException
from .errors.responses import COMMON_ERROR_RESPONSES
from .i18n.timezone import apply_user_timezone
from .models import BaseEntity
from .schemas import BaseEntitySchema, PaginatedResponse
from .tasks import TaskStatusEnum

if TYPE_CHECKING:
    from enum import Enum

logger = logging.getLogger(__name__)


def as_page(
    items: list,
    total_count: int | None = None,
    offset: int = 0,
    limit: int = Settings.page_max_limit,
) -> PaginatedResponse:
    """Convert a list of items into a paginated response."""
    return PaginatedResponse(
        items=items,
        total=total_count or len(items),
        offset=offset,
        limit=limit,
    )


class AbstractBaseRouter(metaclass=singleton.Singleton):
    """
    Abstract base router for CRUD operations with FastAPI.

    Provides standard REST endpoints: list, retrieve, create, update, delete.
    """

    model: type[BaseEntity]
    schema: type[BaseEntitySchema] | None

    unique_per_user: bool = False
    create_mine_if_not_found: bool = False

    def __init__(
        self,
        *,
        model: type[BaseEntity] | None = None,
        schema: type[BaseEntitySchema] | None = None,
        user_dependency: Callable[[Request], object] | None = None,
        prefix: str | None = None,
        tags: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        """
        Initialize abstract base router.

        Args:
            model: Entity model class.
            schema: Pydantic schema class.
            user_dependency: Optional user dependency function.
            prefix: URL prefix for routes.
            tags: OpenAPI tags for routes.
            **kwargs: Additional keyword arguments.

        """
        if model is None:
            if self.model is None:
                raise ValueError(
                    f"model is required in {self.__class__.__name__} "
                    "router class"
                )
        else:
            self.model = model
        if schema is None:
            if self.schema is None:
                raise ValueError(
                    f"schema is required in {self.__class__.__name__} "
                    "router class"
                )
        else:
            self.schema = schema

        self.user_dependency = user_dependency
        if prefix is None:
            prefix = f"/{self.model.__name__.lower()}s"
        if tags is None:
            tags = [self.model.__name__]

        route_option_keys = (
            "list_route",
            "retrieve_route",
            "create_route",
            "update_route",
            "delete_route",
            "statistics_route",
            "mine_route",
        )
        schema_option_keys = (
            "list_item_schema",
            "list_response_schema",
            "retrieve_response_schema",
            "create_response_schema",
            "update_response_schema",
            "delete_response_schema",
            "create_request_schema",
            "update_request_schema",
        )
        route_options = {
            key: kwargs.pop(key) for key in route_option_keys if key in kwargs
        }
        schema_options = {
            key: kwargs.pop(key) for key in schema_option_keys if key in kwargs
        }
        # Avoid clobbering the resolved URL prefix with route-local prefix.
        kwargs.pop("prefix", None)

        self.router = APIRouter(
            prefix=prefix,
            tags=cast("list[str | Enum]", tags),
            responses=cast(
                "Any", kwargs.pop("responses", COMMON_ERROR_RESPONSES)
            ),
            **cast("Any", kwargs),
        )

        self.config_schemas(self.schema, **cast("Any", schema_options))
        self.config_routes(**cast("Any", route_options))

    def config_schemas(
        self, schema: type[BaseEntitySchema], **kwargs: object
    ) -> None:
        """
        Configure Pydantic schemas for request/response validation.

        Args:
            schema: Base schema class.
            **kwargs: Optional schema overrides for specific operations.

        """
        self.schema = schema
        self.list_item_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("list_item_schema", schema)
        )
        list_response = kwargs.get("list_response_schema")
        if list_response is None:
            list_response = PaginatedResponse[Any]
        self.list_response_schema: type[BaseModel] = cast(
            "type[BaseModel]", list_response
        )
        self.retrieve_response_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("retrieve_response_schema", schema)
        )
        self.create_response_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("create_response_schema", schema)
        )
        self.update_response_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("update_response_schema", schema)
        )
        self.delete_response_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("delete_response_schema", schema)
        )

        self.create_request_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("create_request_schema", schema)
        )
        self.update_request_schema: type[BaseModel] = cast(
            "type[BaseModel]", kwargs.get("update_request_schema", schema)
        )

    def config_routes(
        self,
        *,
        prefix: str = "",
        list_route: bool = True,
        retrieve_route: bool = True,
        create_route: bool = True,
        update_route: bool = True,
        delete_route: bool = True,
        statistics_route: bool = False,
        mine_route: bool = False,
        **_kwargs: object,
    ) -> None:
        """
        Configure FastAPI routes for CRUD operations.

        Args:
            prefix: URL prefix for routes.
            list_route: Enable GET / endpoint for listing.
            retrieve_route: Enable GET /{uid} endpoint.
            create_route: Enable POST / endpoint.
            update_route: Enable PATCH /{uid} endpoint.
            delete_route: Enable DELETE /{uid} endpoint.
            statistics_route: Enable GET /statistics endpoint.
            mine_route: Enable GET /mine endpoint.
            **_kwargs: Additional keyword arguments.

        """
        prefix = prefix.strip("/")
        prefix = f"/{prefix}" if prefix else ""

        if list_route:
            self.router.add_api_route(
                f"{prefix}",
                self.list_items,
                methods=["GET"],
                response_model=self.list_response_schema,
                status_code=200,
            )

        if mine_route:
            self.router.add_api_route(
                f"{prefix}/mine",
                self.mine_items,
                methods=["GET"],
                response_model=(
                    self.retrieve_response_schema
                    if self.unique_per_user
                    else self.list_response_schema
                ),
                status_code=200,
            )

        if statistics_route:
            self.router.add_api_route(
                f"{prefix}/statistics",
                self.statistics,
                methods=["GET"],
            )

        if retrieve_route:
            self.router.add_api_route(
                f"{prefix}/{{uid:str}}",
                self.retrieve_item,
                methods=["GET"],
                response_model=self.retrieve_response_schema,
                status_code=200,
            )

        if create_route:
            self.router.add_api_route(
                f"{prefix}",
                self.create_item,
                methods=["POST"],
                response_model=self.create_response_schema,
                status_code=201,
            )

        if update_route:
            self.router.add_api_route(
                f"{prefix}/{{uid:str}}",
                self.update_item,
                methods=["PATCH"],
                response_model=self.update_response_schema,
                status_code=200,
            )

        if delete_route:
            self.router.add_api_route(
                f"{prefix}/{{uid:str}}",
                self.delete_item,
                methods=["DELETE"],
                response_model=self.delete_response_schema,
            )

    async def get_item(
        self,
        uid: str,
        *,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> BaseEntity:
        """
        Get an item by UID, raising exception if not found.

        Args:
            uid: Unique identifier.
            user_id: Optional user ID filter.
            tenant_id: Optional tenant ID filter.
            is_deleted: Filter by deletion status.
            **kwargs: Additional filter parameters.

        Returns:
            Entity instance.

        Raises:
            BaseHTTPException: If item is not found (404).

        """
        item = await self.model.get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **cast("Any", kwargs),
        )
        if item is None:
            raise BaseHTTPException(
                status_code=404,
                error_code="item_not_found",
                message={
                    "en": f"{self.model.__name__.capitalize()} not found"
                },
            )
        return item

    async def get_user(
        self, request: Request, **_kwargs: object
    ) -> object | None:
        """
        Get user from request using user_dependency.

        Args:
            request: FastAPI request object.
            **_kwargs: Additional keyword arguments.

        Returns:
            User object or None if no user_dependency is configured.

        """
        if self.user_dependency is None:
            return None
        if inspect.iscoroutinefunction(self.user_dependency):
            user = await self.user_dependency(request)
        else:
            user = self.user_dependency(request)
        apply_user_timezone(request, user)
        return user

    async def get_user_id(
        self, request: Request, **_kwargs: object
    ) -> str | None:
        """
        Get user ID from request.

        Args:
            request: FastAPI request object.
            **_kwargs: Additional keyword arguments.

        Returns:
            User ID string or None.

        """
        user = await self.get_user(request)
        if user is None:
            return None
        return cast("str | None", getattr(user, "uid", None))

    async def _statistics(
        self,
        request: Request,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
        **kwargs: object,
    ) -> dict:
        """
        Get statistics about items matching filters.

        Args:
            request: FastAPI request object.
            created_at_from: Optional start date filter.
            created_at_to: Optional end date filter.
            **kwargs: Additional filter parameters.

        Returns:
            Dictionary with total count and filter parameters.

        """
        params: dict[str, Any] = dict(request.query_params)
        if "is_deleted" in params:
            params["is_deleted"] = params["is_deleted"].lower() == "true"
        if created_at_from is not None:
            params["created_at_from"] = created_at_from
        if created_at_to is not None:
            params["created_at_to"] = created_at_to

        return {
            "total": await self.model.total_count(
                **params, **cast("Any", kwargs)
            ),
            **params,
        }

    async def statistics(
        self,
        request: Request,
        created_at_from: datetime | None = None,
        created_at_to: datetime | None = None,
    ) -> dict:
        """
        Public statistics endpoint handler.

        Args:
            request: FastAPI request object.
            created_at_from: Optional start date filter.
            created_at_to: Optional end date filter.

        Returns:
            Dictionary with statistics.

        """
        return await self._statistics(
            request=request,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
        )

    async def _list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        **kwargs: object,
    ) -> PaginatedResponse[BaseModel]:
        """
        List items with pagination (internal helper).

        Args:
            request: FastAPI request object.
            offset: Starting offset.
            limit: Maximum number of items.
            **kwargs: Additional filter parameters.

        Returns:
            PaginatedResponse with items and metadata.

        """
        user_id = kwargs.pop("user_id", await self.get_user_id(request))
        limit = max(1, min(limit, Settings.page_max_limit))

        items, total = await self.model.list_total_combined(
            user_id=cast("str | None", user_id),
            offset=offset,
            limit=limit,
            **cast("Any", kwargs),
        )
        items_in_schema = [
            self.list_item_schema(**item.model_dump()) for item in items
        ]

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
    ) -> PaginatedResponse[Any]:
        """
        List items endpoint handler.

        Args:
            request: FastAPI request object.
            offset: Starting offset for pagination.
            limit: Maximum number of items to return.
            created_at_from: Optional start date filter.
            created_at_to: Optional end date filter.

        Returns:
            PaginatedResponse with items and metadata.

        """
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
        uid: str,
    ) -> BaseEntity:
        """
        Retrieve a single item by UID.

        Args:
            request: FastAPI request object.
            uid: Unique identifier.

        Returns:
            Entity instance.

        """
        user_id = await self.get_user_id(request)
        return await self.get_item(uid=uid, user_id=user_id)

    async def create_item(
        self,
        request: Request,
        data: dict,
    ) -> BaseEntity:
        """
        Create a new item.

        Args:
            request: FastAPI request object.
            data: Item data dictionary or Pydantic model.

        Returns:
            Created entity instance.

        """
        user_id = await self.get_user_id(request)
        if isinstance(data, BaseModel):
            data = data.model_dump()
        from .audit.context import audit_actor_scope

        with audit_actor_scope(user_id=user_id):
            return await self.model.create_item({**data, "user_id": user_id})

    async def update_item(
        self,
        request: Request,
        uid: str,
        data: dict,
    ) -> BaseEntity:
        """
        Update an existing item.

        Args:
            request: FastAPI request object.
            uid: Unique identifier.
            data: Update data dictionary or Pydantic model.

        Returns:
            Updated entity instance.

        """
        user_id = await self.get_user_id(request)
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)
        item = await self.get_item(uid=uid, user_id=user_id)
        from .audit.context import audit_actor_scope

        with audit_actor_scope(user_id=user_id):
            return await self.model.update_item(item, data)

    async def delete_item(
        self,
        request: Request,
        uid: str,
    ) -> BaseEntity:
        """
        Delete an item (soft delete).

        Args:
            request: FastAPI request object.
            uid: Unique identifier.

        Returns:
            Deleted entity instance.

        """
        user_id = await self.get_user_id(request)
        item = await self.get_item(uid=uid, user_id=user_id)

        from .audit.context import audit_actor_scope

        with audit_actor_scope(user_id=user_id):
            return await self.model.delete_item(item)

    async def mine_items(
        self,
        request: Request,
    ) -> PaginatedResponse[BaseModel] | BaseModel:
        """
        Get items owned by the current user.

        Args:
            request: FastAPI request object.

        Returns:
            PaginatedResponse with user's items, or single item if
            unique_per_user.

        """
        user_id = await self.get_user_id(request)
        resp = await self._list_items(request=request, user_id=user_id)
        if resp.total == 0 and self.create_mine_if_not_found:
            resp.items = [await self.model.create_item({"user_id": user_id})]
            resp.total = 1
        if self.unique_per_user:
            return resp.items[0]
        return resp


class AbstractTaskRouter(AbstractBaseRouter):
    """Abstract router for task-based entities with processing capabilities."""

    def __init__(
        self,
        *,
        model: type[BaseEntity] | None = None,
        schema: type[BaseEntitySchema] | None = None,
        user_dependency: Callable[[Request], object] | None = None,
        draftable: bool = True,
        **kwargs: object,
    ) -> None:
        """
        Initialize task router.

        Args:
            model: Entity model class.
            schema: Pydantic schema class.
            user_dependency: Optional user dependency function.
            draftable: Whether tasks can be created in draft status.
            **kwargs: Additional keyword arguments.

        """
        self.draftable = draftable
        super().__init__(
            model=model,
            user_dependency=user_dependency,
            schema=schema,
            **cast("Any", kwargs),
        )

    def config_routes(self, **kwargs: object) -> None:
        """
        Configure routes for task router with additional endpoints.

        Args:
            **kwargs: Additional keyword arguments.

        """
        create_route = bool(kwargs.pop("create_route", True))
        kwargs["create_route"] = False
        super().config_routes(**cast("Any", kwargs))

        if create_route:
            self.router.add_api_route(
                "",
                self.create_task_item,
                methods=["POST"],
                response_model=self.create_response_schema,
                status_code=201,
            )

        if self.draftable and kwargs.get("start_route", True):
            self.router.add_api_route(
                "/{uid:str}/start",
                self.start_item,
                methods=["POST"],
                response_model=self.retrieve_response_schema,
            )

        if kwargs.get("webhook_route", True):
            self.router.add_api_route(
                "/{uid:str}/webhook",
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
    ) -> dict:
        """
        Get statistics for task items.

        Args:
            request: FastAPI request object.
            created_at_from: Optional start date filter.
            created_at_to: Optional end date filter.
            task_status: Optional task status filter.

        Returns:
            Dictionary with statistics.

        """
        extra: dict[str, object] = {}
        if task_status is not None:
            extra["task_status"] = task_status
        return await self._statistics(
            request=request,
            created_at_from=created_at_from,
            created_at_to=created_at_to,
            **extra,
        )

    async def create_task_item(
        self,
        request: Request,
        data: dict,
        background_tasks: BackgroundTasks,
        blocking: bool = False,
    ) -> BaseEntity:
        """HTTP create endpoint that can start task processing."""
        return await self._create_task_item(
            request,
            data,
            background_tasks=background_tasks,
            blocking=blocking,
        )

    async def _create_task_item(
        self,
        request: Request,
        data: dict,
        *,
        background_tasks: BackgroundTasks | None = None,
        blocking: bool = False,
    ) -> BaseEntity:
        """Create a task item and optionally start processing."""
        if not self.draftable:
            data["task_status"] = "init"

        item = await super().create_item(request, data)

        if item.task_status == "init" or not self.draftable:
            if blocking:
                await item.start_processing()
            elif background_tasks is not None:
                background_tasks.add_task(item.start_processing)
        return item

    async def create_item(
        self,
        request: Request,
        data: dict,
    ) -> BaseEntity:
        """Create a task item without starting background processing."""
        return await self._create_task_item(request, data)

    async def start_item(
        self, request: Request, uid: str, background_tasks: BackgroundTasks
    ) -> dict:
        """
        Start processing a task item.

        Args:
            request: FastAPI request object.
            uid: Task unique identifier.
            background_tasks: FastAPI background tasks.

        Returns:
            Task item as dictionary.

        """
        user_id = await self.get_user_id(request)
        item = await self.get_item(uid=uid, user_id=user_id)
        background_tasks.add_task(item.start_processing)
        return item.model_dump()

    async def webhook(
        self,
        _request: Request,
        uid: str,
        data: dict,
    ) -> dict:
        """
        Handle webhook callbacks for task items.

        Args:
            request: FastAPI request object.
            uid: Task unique identifier.
            data: Webhook data dictionary.

        Returns:
            Response dictionary with webhook confirmation.

        """

        logger.info("Webhook received for %s with data %s", uid, data)
        return {"message": f"Webhook received for {uid} with data", **data}


def copy_router(router: APIRouter, new_prefix: str) -> APIRouter:
    """
    Create a copy of a router with a new prefix.

    Args:
        router: Source APIRouter instance.
        new_prefix: New URL prefix for the copied router.

    Returns:
        New APIRouter instance with updated prefix.

    """
    new_router = APIRouter(prefix=new_prefix)
    for route in router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        path = getattr(route, "path", "")
        if router.prefix and path.startswith(router.prefix):
            path = path[len(router.prefix) :] or "/"
        methods = getattr(route, "methods", None)
        new_router.add_api_route(
            path,
            endpoint,
            methods=list(methods) if methods else None,
            response_model=getattr(route, "response_model", None),
            status_code=getattr(route, "status_code", None),
            tags=getattr(route, "tags", None),
            name=getattr(route, "name", None),
            include_in_schema=getattr(route, "include_in_schema", True),
        )

    return new_router
