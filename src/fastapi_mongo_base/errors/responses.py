"""OpenAPI error response schemas aligned with exception handlers."""

import fastapi
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, ConfigDict, Field

from . import status as _status_errors
from .base import BaseHTTPException


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
    input: object = None
    ctx: dict[str, object] | None = None


class ValidationErrorResponseModel(BaseModel):
    """Structured validation error response."""

    message: dict[str, str]
    error_code: str = "validation_error"
    detail: str | None = None
    reasons: list[ValidationReason] = Field(default_factory=list)


class InternalErrorResponseModel(BaseModel):
    """Fallback response for unhandled exceptions."""

    message: str
    error: str = "Exception"


def _status_error_descriptions() -> dict[int, str]:
    """Map HTTP status codes to OpenAPI descriptions from status exceptions."""
    descriptions: dict[int, set[str]] = {}
    for name in dir(_status_errors):
        exc_type = getattr(_status_errors, name)
        if not (
            isinstance(exc_type, type)
            and issubclass(exc_type, BaseHTTPException)
        ):
            continue
        code = exc_type.status_code
        if not isinstance(code, int):
            continue
        label = exc_type.message_en or name
        descriptions.setdefault(code, set()).add(label)
    return {
        code: " / ".join(sorted(labels))
        for code, labels in descriptions.items()
    }


COMMON_ERROR_RESPONSES: dict[int, dict[str, object]] = {
    code: {
        "model": APIErrorResponseModel,
        "description": description,
    }
    for code, description in _status_error_descriptions().items()
}
COMMON_ERROR_RESPONSES[422] = {
    "model": ValidationErrorResponseModel,
    "description": "Validation error",
}


def _patch_validation_responses(schema: dict[str, object]) -> None:
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

    def custom_openapi() -> dict[str, object]:
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
