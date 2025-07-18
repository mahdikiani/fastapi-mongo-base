import os

from fastapi import Request
from pydantic import BaseModel

from ..core import config, exceptions
from ..routes import AbstractBaseRouter
from ..schemas import PaginatedResponse

try:
    from usso import UserData, authorization
    from usso.config import APIHeaderConfig, AuthConfig
    from usso.exceptions import USSOException
    from usso.integrations.fastapi import USSOAuthentication
except ImportError as e:
    raise ImportError("USSO is not installed") from e


class PermissionDenied(exceptions.BaseHTTPException):
    def __init__(
        self,
        error: str = "permission_denied",
        message: dict = None,
        detail: str = None,
        **kwargs,
    ):
        super().__init__(
            403, error=error, message=message, detail=detail, **kwargs
        )


class AbstractTenantUSSORouter(AbstractBaseRouter):
    resource: str | None = None

    @property
    def resource_path(self):
        namespace = (
            getattr(self, "namespace", None) or os.getenv("namespace") or ""
        )
        service = getattr(self, "service", None) or os.getenv("service") or ""
        resource = self.resource or self.model.__name__.lower() or ""
        return f"{namespace}/{service}/{resource}".lstrip("/")

    async def get_user(self, request: Request, **kwargs) -> UserData:
        usso = USSOAuthentication(
            jwt_config=AuthConfig(
                jwks_url=(
                    f"https://usso.uln.me/.well-known/jwks.json?domain={request.url.hostname}"
                ),
                api_key_header=APIHeaderConfig(
                    type="CustomHeader",
                    name="x-api-key",
                    verify_endpoint="https://usso.uln.me/api/sso/v1/apikeys/verify",
                ),
            )
        )
        return usso(request)

    async def authorize(
        self,
        *,
        action: str,
        user: UserData | None = None,
        filter_data: dict | None = None,
    ) -> bool:
        if user is None:
            raise USSOException(401, "unauthorized")
        user_scopes = user.scopes or []
        if not authorization.check_access(
            user_scopes=user_scopes,
            resource_path=self.resource_path,
            action=action,
            filters=filter_data,
        ):
            raise PermissionDenied(
                detail=f"User {user.uid} is not authorized to "
                f"{action} {self.resource_path}"
            )
        return True

    def get_list_filter_queries(
        self, *, user: UserData, self_access: bool = True
    ) -> dict:
        matched_scopes: list[dict] = authorization.get_scope_filters(
            action="read", resource=self.resource_path, user_scopes=user.scopes
        )
        if self_access:
            matched_scopes.append({"user_id": user.uid})
        elif not matched_scopes:
            return {"__deny__": True}  # no access to any resource

        return authorization.broadest_scope_filter(matched_scopes)

    async def get_item(
        self,
        uid: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        **kwargs,
    ):
        item = await self.model.get_item(
            uid=uid,
            user_id=user_id,
            tenant_id=tenant_id,
            ignore_user_id=True,
            **kwargs,
        )
        if item is None:
            raise exceptions.BaseHTTPException(
                status_code=404,
                error="item_not_found",
                message=f"{self.model.__name__.capitalize()} not found",
            )
        return item

    async def _list_items(
        self, request: Request, offset: int = 0, limit: int = 10, **kwargs
    ):
        user = await self.get_user(request)
        limit = max(1, min(limit, config.Settings.page_max_limit))

        filters = self.get_list_filter_queries(user=user)
        if filters.get("__deny__"):
            return PaginatedResponse(
                items=[],
                total=0,
                offset=offset,
                limit=limit,
            )

        items, total = await self.model.list_total_combined(
            offset=offset,
            limit=limit,
            **(kwargs | filters),
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

    async def retrieve_item(self, request: Request, uid: str):
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )
        await self.authorize(
            action="read",
            user=user,
            filter_data=item.model_dump(
                include=["uid", "tenant_id", "user_id", "workspace_id"]
            ),
        )
        return item

    async def create_item(self, request: Request, data: dict):
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump()
        await self.authorize(action="create", user=user, filter_data={})
        item = await self.model.create_item({
            **data,
            "user_id": user.user_id,
            "tenant_id": user.tenant_id,
        })
        return item

    async def update_item(self, request: Request, uid: str, data: dict):
        user = await self.get_user(request)
        if isinstance(data, BaseModel):
            data = data.model_dump()
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )
        await self.authorize(
            action="update",
            user=user,
            filter_data=item.model_dump(
                include=["uid", "tenant_id", "user_id", "workspace_id"]
            ),
        )
        item = await self.model.update_item(item, data)
        return item

    async def delete_item(self, request: Request, uid: str):
        user = await self.get_user(request)
        item = await self.get_item(
            uid=uid, user_id=None, tenant_id=user.tenant_id
        )

        await self.authorize(
            action="delete",
            user=user,
            filter_data=item.model_dump(
                include=["uid", "tenant_id", "user_id", "workspace_id"]
            ),
        )
        item = await self.model.delete_item(item)
        return item
