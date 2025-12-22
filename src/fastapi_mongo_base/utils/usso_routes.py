"""Authenticated router using USSO for FastAPI MongoDB base package."""

import os

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


class AbstractTenantUSSORouter(AbstractBaseRouter):
    """
    Abstract base class for USSO routes.

    Attributes:
        namespace: The namespace of the resource.
        service: The service of the resource.
        resource: The resource name.
        self_action: The action to authorize the user to do action on the
                     owned resource. (user_id == resource.user_id).
                     Default is "owner".
        self_access: Whether to allow access to the resource by the user itself
                     in list queries. (user_id == resource.user_id).

    """

    resource: str | None = None
    self_action: str = "owner"
    self_access: bool = True

    @property
    def resource_path(self) -> str:
        """
        Get the resource path for the USSO routes.

        Returns:
            Resource path.
        """
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
        """
        Get the user for the USSO routes.

        Args:
            request: The request.
            **kwargs: Additional keyword arguments.

        Returns:
            User.
        """
        usso_base_url = os.getenv("USSO_BASE_URL") or "https://usso.uln.me"

        usso = USSOAuthentication(
            jwt_config=AuthConfig(
                jwks_url=(f"{usso_base_url}/.well-known/jwks.json"),
                api_key_header=APIHeaderConfig(
                    header_name="x-api-key",
                    verify_endpoint=(
                        f"{usso_base_url}/api/sso/v1/apikeys/verify"
                    )
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
        Authorize the user to perform the action on the resource.

        Args:
            action: The action to authorize the user to do.
            user: The user to authorize.
            filter_data: The filter data to authorize the user to do.
            raise_exception: Whether to raise an exception if the user
            is not authorized.

        Returns:
            True if the user is authorized to perform the action on
            the resource, False otherwise.
        """
        if user is None:
            if raise_exception:
                raise USSOException(401, "unauthorized")
            return False
        if authorization.owner_authorization(
            requested_filter=filter_data,
            user_id=user.uid,
            self_action=self.self_action,
            action=action,
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
        """
        Get the list filter queries for the USSO routes.

        Args:
            user: The user to get the list filter queries for.

        Returns:
            List filter queries.
        """
        matched_scopes: list[dict] = authorization.get_scope_filters(
            action="read",
            resource=self.resource_path,
            user_scopes=user.scopes if user else [],
        )
        if self.self_access and hasattr(self.model, "user_id"):
            matched_scopes.append({"user_id": user.uid})
        elif not matched_scopes:
            return {"__deny__": True}  # no access to any resource

        return authorization.broadest_scope_filter(matched_scopes)

    async def get_item(
        self,
        uid: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        is_deleted: bool = False,
        **kwargs: object,
    ) -> BaseEntity:
        """
        Get the item for the USSO routes.

        Args:
            uid: The UID of the item.
            user_id: The user ID of the item.
            tenant_id: The tenant ID of the item.
            is_deleted: The deletion status of the item.
            **kwargs: Additional keyword arguments.

        Returns:
            Item.
        """
        item = await self.model.get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            is_deleted=is_deleted,
            ignore_user_id=kwargs.pop("ignore_user_id", True),
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
        Get the list items for the USSO routes.

        Args:
            request: The request.
            offset: The offset of the items.
            limit: The limit of the items.
            **kwargs: Additional keyword arguments.

        Returns:
            List items.
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
                items=[],
                total=0,
                offset=offset,
                limit=limit,
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
        Retrieve the item for the USSO routes.

        Args:
            request: The request.
            uid: The UID of the item.

        Returns:
            Item.
        """
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )
        await self.authorize(
            action="read",
            user=user,
            filter_data=item.model_dump(),
        )
        return item

    async def create_item(self, request: Request, data: dict) -> BaseEntity:
        """
        Create the item for the USSO routes.

        Args:
            request: The request.
            data: The data to create the item.

        Returns:
            Item.
        """
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump()
        await self.authorize(action="create", user=user, filter_data=data)
        item = await self.model.create_item({
            **data,
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
        })
        return item

    async def update_item(
        self, request: Request, uid: str, data: dict
    ) -> BaseEntity:
        """
        Update the item for the USSO routes.

        Args:
            request: The request.
            uid: The UID of the item.
            data: The data to update the item.

        Returns:
            Item.
        """
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump(exclude_unset=True)
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )
        await self.authorize(
            action="update",
            user=user,
            filter_data=item.model_dump(),
        )
        item = await self.model.update_item(item, data)
        return item

    async def delete_item(self, request: Request, uid: str) -> BaseEntity:
        """
        Delete the item for the USSO routes.

        Args:
            request: The request.
            uid: The UID of the item.

        Returns:
            Item.
        """
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )

        await self.authorize(
            action="delete",
            user=user,
            filter_data=item.model_dump(),
        )
        item = await self.model.delete_item(item)
        return item

    async def mine_items(
        self,
        request: Request,
    ) -> PaginatedResponse[BaseModel] | BaseModel:
        """
        Get the items for the USSO routes.

        Args:
            request: The request.

        Returns:
            Items.
        """
        user = await self.get_user(request)
        resp = await self._list_items(
            request=request,
            user_id=user.uid,
        )
        if resp.total == 0 and self.create_mine_if_not_found:
            resp.items = [
                await self.model.create_item({
                    "user_id": user.uid,
                    "tenant_id": user.tenant_id,
                })
            ]
            resp.total = 1
        if self.unique_per_user:
            return resp.items[0]
        return resp
