"""Authenticated router using USSO for FastAPI MongoDB base package."""

import os
from collections.abc import Callable

from fastapi import Request
from pydantic import BaseModel

from ..core import config, exceptions
from ..models import BaseEntity
from ..routes import AbstractBaseRouter
from ..schemas import PaginatedResponse

try:
    from usso import UserData, authorization
    from usso.config import APIHeaderConfig, AuthConfig
    from usso.exceptions import PermissionDenied, USSOException
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
        return self.get_owner_id(user)

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
        return usso(request)

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
            USSOException: If the user is not authorized and
                           raise_exception is True.
            PermissionDenied: If the user is not authorized and
                              raise_exception is False.
        """
        if user is None:
            if raise_exception:
                raise USSOException(401, "unauthorized")
            return False
        owner_id = self.get_owner_id(user)
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
                raise PermissionDenied(
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
            matched_scopes.append({self.owner_attr: self.get_owner_id(user)})
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
            raise exceptions.BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message={
                    "en": f"{self.model.__name__.capitalize()} not found"
                },
            )
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
            raise exceptions.BaseHTTPException(
                status_code=403,
                error="forbidden",
                message={
                    "en": "You are not authorized to access this resource"
                },
            )
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
            PermissionDenied: If the user is not authorized
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
            USSOException: If the user is not authorized to create the item.
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
            USSOException: If the user is not authorized to update the item.
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
            USSOException: If the user is not authorized to delete the item.
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
        owner_id = self.get_owner_id(user)
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
    """

    owner_attr: str = "owner_id"
    get_owner_id: Callable[
        [type["AbstractOwnedUSSORouter"], UserData], str
    ] = lambda self, u: u.workspace_id or u.user_id
    get_owner_id_for_create: (
        Callable[[type["AbstractOwnedUSSORouter"], UserData], str] | None
    ) = None  # same as get_owner_id
