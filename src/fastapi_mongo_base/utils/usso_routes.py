import os
from typing import TypeVar

from fastapi import Request
from pydantic import BaseModel

from ..core import config, exceptions
from ..models import BaseEntity
from ..routes import AbstractBaseRouter
from ..schemas import BaseEntitySchema, PaginatedResponse

try:
    from usso import UserData, authorization
    from usso.config import APIHeaderConfig, AuthConfig
    from usso.exceptions import USSOException
    from usso.integrations.fastapi import USSOAuthentication
except ImportError as e:
    raise ImportError("USSO is not installed") from e

T = TypeVar("T", bound=BaseEntity)
TS = TypeVar("TS", bound=BaseEntitySchema)
TSCHEMA = TypeVar("TSCHEMA", bound=BaseModel)


class PermissionDenied(exceptions.BaseHTTPException):
    def __init__(
        self,
        error: str = "permission_denied",
        message: dict | None = None,
        detail: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            403, error=error, message=message, detail=detail, **kwargs
        )


BASE_USSO_URL = os.getenv("BASE_USSO_URL") or "https://usso.uln.me"


class AbstractTenantUSSORouter(AbstractBaseRouter):
    resource: str | None = None
    self_action: str = "owner"

    @property
    def resource_path(self) -> str:
        namespace = (
            getattr(self, "namespace", None)
            or os.getenv("USSO_NAMESPACE")
            or ""
        )
        service = (
            getattr(self, "service", None) or os.getenv("USSO_SERVICE") or ""
        )
        resource = self.resource or self.model.__name__.lower() or ""
        return f"{namespace}/{service}/{resource}".lstrip("/")

    async def get_user(self, request: Request, **kwargs: object) -> UserData:
        usso = USSOAuthentication(
            jwt_config=AuthConfig(
                jwks_url=(
                    f"{BASE_USSO_URL}/.well-known/jwks.json"
                    # f"?domain={request.url.hostname}"
                ),
                api_key_header=APIHeaderConfig(
                    type="CustomHeader",
                    name="x-api-key",
                    verify_endpoint=(
                        f"{BASE_USSO_URL}/api/sso/v1/apikeys/verify"
                    ),
                ),
            ),
            from_base_usso_url=BASE_USSO_URL,
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
            raise PermissionDenied(
                detail=f"User {user.uid} is not authorized to "
                f"{action} {self.resource_path}"
            )
        return True

    def get_list_filter_queries(
        self, *, user: UserData, self_access: bool = True
    ) -> dict:
        matched_scopes: list[dict] = authorization.get_scope_filters(
            action="read",
            resource=self.resource_path,
            user_scopes=user.scopes or [],
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
        **kwargs: object,
    ) -> T:
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
    ) -> PaginatedResponse[TS]:
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

    async def retrieve_item(self, request: Request, uid: str) -> T:
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

    async def create_item(self, request: Request, data: dict) -> T:
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

    async def update_item(self, request: Request, uid: str, data: dict) -> T:
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

    async def delete_item(self, request: Request, uid: str) -> T:
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
