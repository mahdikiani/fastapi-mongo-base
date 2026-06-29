"""OpenAPI error response schemas aligned with exception handlers."""

from typing import Any

import fastapi
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field


class APIErrorResponseModel(BaseModel):
    """Structured error response for BaseHTTPException handlers."""

    model_config = ConfigDict(extra="allow")

    message: dict[str, str]
    error_code: str
    detail: str | None = None


class ValidationReason(BaseModel):
    """Single field validation failure."""

    model_config = ConfigDict(extra="allow")

    field: str
    type: str | None = None
    msg: str | None = None
    input: Any = None
    ctx: dict[str, Any] | None = None


class ValidationErrorResponseModel(BaseModel):
    """Structured validation error response."""

    message: dict[str, str]
    error_code: str = "validation_error"
    detail: None = None
    reasons: list[ValidationReason] = Field(default_factory=list)


class InternalErrorResponseModel(BaseModel):
    """Fallback response for unhandled exceptions."""

    message: str
    error: str = "Exception"


COMMON_ERROR_RESPONSES: dict[int, dict[str, Any]] = {
    400: {
        "model": APIErrorResponseModel,
        "description": "Bad request",
    },
    401: {
        "model": APIErrorResponseModel,
        "description": "Unauthorized",
    },
    402: {
        "model": APIErrorResponseModel,
        "description": "Payment required",
    },
    403: {
        "model": APIErrorResponseModel,
        "description": "Forbidden",
    },
    404: {
        "model": APIErrorResponseModel,
        "description": "Not found",
    },
    409: {
        "model": APIErrorResponseModel,
        "description": "Conflict",
    },
    410: {
        "model": APIErrorResponseModel,
        "description": "Gone",
    },
    422: {
        "model": ValidationErrorResponseModel,
        "description": "Validation error",
    },
    423: {
        "model": APIErrorResponseModel,
        "description": "Locked",
    },
    500: {
        "model": APIErrorResponseModel,
        "description": "Internal server error",
    },
}


def _patch_validation_responses(schema: dict[str, Any]) -> None:
    validation_ref = {
        "$ref": "#/components/schemas/ValidationErrorResponseModel"
    }
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict) or "422" not in responses:
                continue
            responses["422"] = {
                "description": "Validation error",
                "content": {
                    "application/json": {
                        "schema": validation_ref,
                    },
                },
            }


def setup_openapi_errors(app: fastapi.FastAPI) -> None:
    """
    Replace default FastAPI validation error schemas in OpenAPI.

    Args:
        app: FastAPI application instance.

    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        _patch_validation_responses(schema)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = custom_openapi
