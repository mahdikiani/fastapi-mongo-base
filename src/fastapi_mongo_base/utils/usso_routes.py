"""Authenticated router using USSO for FastAPI MongoDB base package."""

import os
from collections.abc import Callable

from fastapi import Request
from pydantic import BaseModel

from ..core import config
from ..errors.status import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from ..i18n.timezone import apply_user_timezone
from ..models import BaseEntity
from ..routes import AbstractBaseRouter
from ..schemas import PaginatedResponse
from .usso.principals import is_service_user

try:
    from usso import UserData, authorization
    from usso.config import APIHeaderConfig, AuthConfig
    from usso.integrations.fastapi import USSOAuthentication
except ImportError as e:
    raise ImportError("USSO is not installed") from e


class AbstractUSSORouterBase(AbstractBaseRouter):
    """
    Abstract base for USSO-authenticated routes with configurable ownership.

    Subclasses configure ownership via:
    - owner_attr: model field used for ownership ("user_id" or "owner_id").
    - get_owner_id: (self, user) -> str used for authorization and filters.
    - get_owner_id_for_create: (self, user) -> str for create
      (default: get_owner_id).
    """

    def _resolve_owner_id(self, user: UserData) -> str:
        """Resolve owner id. Override in subclasses for custom validation."""
        return self.get_owner_id(user)

    resource: str | None = None
    self_action: str = "owner"
    self_access: bool = True

    # Override in subclasses: "user_id" or "owner_id"
    owner_attr: str = "user_id"

    get_owner_id: Callable[[type["AbstractUSSORouterBase"], UserData], str] = (
        lambda self, u: getattr(u, "uid", u.user_id)
    )
    get_owner_id_for_create: (
        Callable[[type["AbstractUSSORouterBase"], UserData], str] | None
    ) = None  # same as get_owner_id

    def _owner_id_for_create(self, user: UserData) -> str:
        """
        Return owner id to set on new items (may differ from auth owner id).

        Args:
            user: The user data.

        Returns:
            The owner id to set on new items.

        """
        if self.get_owner_id_for_create is not None:
            return self.get_owner_id_for_create(user)
        return self._resolve_owner_id(user)

    @property
    def resource_path(self) -> str:
        """Resource path for USSO (namespace/service/resource)."""
        namespace = (
            getattr(self, "namespace", None)
            or os.getenv("USSO_NAMESPACE")
            or ""
        )
        service = (
            getattr(self, "service", None)
            or os.getenv("USSO_SERVICE")
            or os.getenv("PROJECT_NAME")
            or ""
        )
        resource = self.resource or self.model.__name__.lower() or ""
        return f"{namespace}/{service}/{resource}".lstrip("/")

    async def get_user(self, request: Request, **kwargs: object) -> UserData:
        """Resolve authenticated user from request."""
        usso_base_url = os.getenv("USSO_BASE_URL") or "https://usso.uln.me"
        usso = USSOAuthentication(
            jwt_config=AuthConfig(
                jwks_url=f"{usso_base_url}/.well-known/jwks.json",
                api_key_header=APIHeaderConfig(
                    header_name="x-api-key",
                    verify_endpoint=(
                        f"{usso_base_url}/api/sso/v1/apikeys/verify"
                    ),
                ),
            ),
            from_usso_base_url=usso_base_url,
        )
        user = usso(request)
        apply_user_timezone(request, user)
        return user

    async def authorize(
        self,
        *,
        action: str,
        user: UserData | None = None,
        filter_data: dict | None = None,
        raise_exception: bool = True,
    ) -> bool:
        """
        Authorize the user for the given action.

        Args:
            action: The action to authorize.
            user: The user to authorize.
            filter_data: The filter data to authorize.
            raise_exception: Whether to raise an exception if the user
                             is not authorized (default: True).

        Returns:
            True if the user is authorized, False otherwise.

        Raises:
            UnauthorizedError: If the user is not authorized and
                                 raise_exception is True.
            ForbiddenError: If the user is not authorized and
                            raise_exception is False.

        """
        if user is None:
            if raise_exception:
                raise UnauthorizedError()
            return False
        owner_id = self._resolve_owner_id(user)
        if authorization.owner_authorization(
            requested_filter=filter_data,
            self_action=self.self_action,
            action=action,
            **{self.owner_attr: owner_id},
        ):
            return True
        user_scopes = user.scopes or []
        if not authorization.check_access(
            user_scopes=user_scopes,
            resource_path=self.resource_path,
            action=action,
            filters=filter_data,
        ):
            if raise_exception:
                raise ForbiddenError(
                    detail=f"User {user.uid} is not authorized to "
                    f"{action} {self.resource_path}"
                )
            return False
        return True

    def get_list_filter_queries(self, *, user: UserData) -> dict:
        """Build list query filters from user and scopes."""
        matched_scopes: list[dict] = authorization.get_scope_filters(
            action="read",
            resource=self.resource_path,
            user_scopes=user.scopes if user else [],
        )
        if self.self_access and hasattr(self.model, self.owner_attr):
            matched_scopes.append({
                self.owner_attr: self._resolve_owner_id(user)
            })
        elif not matched_scopes:
            return {"__deny__": True}
        return authorization.broadest_scope_filter(matched_scopes)

    async def get_item(
        self,
        uid: str,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> BaseEntity:
        """Fetch one item by uid; raise if not found."""
        ignore_attr = f"ignore_{self.owner_attr}"
        owner_value = kwargs.pop(self.owner_attr, None)
        ignore_val = kwargs.pop(ignore_attr, True)
        item_kw = {self.owner_attr: owner_value, ignore_attr: ignore_val}
        item = await self.model.get_item(
            uid=uid,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            **item_kw,
            **kwargs,
        )
        if item is None:
            raise NotFoundError()
        return item

    async def _list_items(
        self,
        request: Request,
        offset: int = 0,
        limit: int = 10,
        **kwargs: object,
    ) -> PaginatedResponse[BaseModel]:
        """
        List items with pagination.

        Args:
            request: The request object.
            offset: The offset of the items to list.
            limit: The limit of the items to list.
            **kwargs: Additional keyword arguments.

        Returns:
            The paginated response.

        Raises:
            BaseHTTPException: If the user is not authorized to list the items.

        """
        user = await self.get_user(request)
        limit = max(1, min(limit, config.Settings.page_max_limit))
        filters = self.get_list_filter_queries(user=user)
        if filters.get("__deny__"):
            if kwargs.get("raise_exception", True):
                raise ForbiddenError()
            return PaginatedResponse(
                items=[], total=0, offset=offset, limit=limit
            )

        items, total = await self.model.list_total_combined(
            offset=offset,
            limit=limit,
            tenant_id=user.tenant_id,
            **(kwargs | filters),
        )
        items_in_schema = [
            self.list_item_schema.model_validate(item) for item in items
        ]
        return PaginatedResponse(
            items=items_in_schema,
            total=total,
            offset=offset,
            limit=limit,
        )

    async def retrieve_item(self, request: Request, uid: str) -> BaseEntity:
        """
        Retrieve an item by uid.

        Args:
            request: The request object.
            uid: The uid of the item to retrieve.

        Returns:
            The item.

        Raises:
            BaseHTTPException: If the object is not found.
            ForbiddenError: If the user is not authorized
                            to retrieve the item.

        """
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, tenant_id=user.tenant_id, **{self.owner_attr: None}
        )
        await self.authorize(
            action="read",
            user=user,
            filter_data=item.model_dump(),
        )
        return item

    async def create_item(self, request: Request, data: dict) -> BaseEntity:
        """
        Create an item.

        Args:
            request: The request object.
            data: The data of the item to create.

        Returns:
            The item.

        Raises:
            ForbiddenError: If the user is not authorized to create the item.

        """
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump()
        await self.authorize(action="create", user=user, filter_data=data)
        return await self.model.create_item({
            **data,
            self.owner_attr: self._owner_id_for_create(user),
            "tenant_id": user.tenant_id,
        })

    async def update_item(
        self, request: Request, uid: str, data: dict
    ) -> BaseEntity:
        """
        Update an item.

        Args:
            request: The request object.
            uid: The uid of the item to update.
            data: The data of the item to update.

        Returns:
            The item.

        Raises:
            BaseHTTPException: If the object is not found.
            ForbiddenError: If the user is not authorized to update the item.

        """
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)
        item = await self.get_item(
            uid=uid, tenant_id=user.tenant_id, **{self.owner_attr: None}
        )
        await self.authorize(
            action="update",
            user=user,
            filter_data=item.model_dump(),
        )
        return await self.model.update_item(item, data)

    async def delete_item(self, request: Request, uid: str) -> BaseEntity:
        """
        Delete an item.

        Args:
            request: The request object.
            uid: The uid of the item to delete.

        Returns:
            The item.

        Raises:
            BaseHTTPException: If the object is not found.
            ForbiddenError: If the user is not authorized to delete the item.

        """
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, tenant_id=user.tenant_id, **{self.owner_attr: None}
        )
        await self.authorize(
            action="delete",
            user=user,
            filter_data=item.model_dump(),
        )
        return await self.model.delete_item(item)

    async def mine_items(
        self,
        request: Request,
    ) -> PaginatedResponse[BaseModel] | BaseModel:
        """
        Get items owned by the current user.

        Args:
            request: The request object.

        Returns:
            The items.

        """
        user = await self.get_user(request)
        owner_id = self._resolve_owner_id(user)
        resp = await self._list_items(
            request=request,
            **{self.owner_attr: owner_id},
        )
        if resp.total == 0 and self.create_mine_if_not_found:
            resp.items = [
                await self.model.create_item({
                    self.owner_attr: self._owner_id_for_create(user),
                    "tenant_id": user.tenant_id,
                })
            ]
            resp.total = 1
        if self.unique_per_user:
            return resp.items[0]
        return resp


class AbstractTenantUSSORouter(AbstractUSSORouterBase):
    """
    USSO router where ownership is by user_id (user_id == resource.user_id).

    Attributes:
        namespace: The namespace of the resource.
        service: The service of the resource.
        resource: The resource name.
        self_action: The action for owned resource (default "owner").
        self_access: Allow list access to own resources (default True).

    """

    owner_attr: str = "user_id"
    get_owner_id: Callable[
        [type["AbstractTenantUSSORouter"], UserData], str
    ] = lambda self, u: getattr(u, "uid", u.user_id)
    get_owner_id_for_create: Callable[
        [type["AbstractTenantUSSORouter"], UserData], str
    ] = lambda self, u: u.user_id


class AbstractOwnedUSSORouter(AbstractUSSORouterBase):
    """
    USSO router where ownership is by owner_id (owner_id == resource.owner_id).

    Attributes:
        namespace: The namespace of the resource.
        service: The service of the resource.
        resource: The resource name.
        self_action: The action for owned resource (default "owner").
        self_access: Allow list access to own resources (default True).
        workspace_only: When True, owner_id must be a workspace_id;
                        raises 400 if user has no workspace and no broad
                        resource scope (default False).

    """

    owner_attr: str = "owner_id"
    workspace_only: bool = False

    get_owner_id_for_create: (
        Callable[[type["AbstractOwnedUSSORouter"], UserData], str] | None
    ) = None  # same as get_owner_id

    def get_owner_id(self, user: UserData) -> str | None:
        """
        Resolve owner_id for workspace-scoped resources.

        Service principals (agent, API key) may omit workspace_id; end users
        on workspace-only resources must have a workspace unless they hold
        a broad resource scope.
        """
        if is_service_user(user):
            return user.workspace_id
        if self.workspace_only:
            return user.workspace_id
        return user.workspace_id or user.user_id

    def _has_broad_resource_access(self, user: UserData) -> bool:
        """
        Return True when the user has an unfiltered scope on this resource.

        Users with e.g. ``*:*`` or ``create:ns/service/resource`` (no query
        filters) may operate without ``workspace_id`` in their JWT.
        """
        return authorization.check_access(
            user_scopes=user.scopes or [],
            resource_path=self.resource_path,
            action="read",
            filters=None,
        )

    def _resolve_owner_id(self, user: UserData) -> str | None:
        """Resolve owner_id, raising a clear error if workspace is missing."""
        owner_id = self.get_owner_id(user)
        if (
            self.workspace_only
            and not is_service_user(user)
            and not owner_id
            and not self._has_broad_resource_access(user)
        ):
            raise BadRequestError(
                error_code="workspace_required",
                detail="User must belong to a workspace for this resource",
            )
        return owner_id


class AbstractWorkspaceUSSORouter(AbstractUSSORouterBase):
    """
    USSO router where resources are scoped by workspace_id.

    Requires JWT ``workspace_id`` for end users unless they hold a broad
    resource scope or are a service principal.
    """

    owner_attr: str = "workspace_id"

    def get_owner_id(self, user: UserData) -> str | None:
        """Resolve workspace_id from the authenticated user."""
        if is_service_user(user):
            return user.workspace_id
        return user.workspace_id

    def _has_broad_resource_access(self, user: UserData) -> bool:
        """Return True for unfiltered scope on this resource."""
        return authorization.check_access(
            user_scopes=user.scopes or [],
            resource_path=self.resource_path,
            action="read",
            filters=None,
        )

    def _resolve_owner_id(self, user: UserData) -> str | None:
        """Resolve workspace_id, raising if missing for scoped users."""
        workspace_id = self.get_owner_id(user)
        if (
            not is_service_user(user)
            and not workspace_id
            and not self._has_broad_resource_access(user)
        ):
            raise BadRequestError(
                error_code="workspace_required",
                detail="User must belong to a workspace for this resource",
            )
        return workspace_id
