"""Tests for OpenAPI error response schemas."""

from fastapi.testclient import TestClient

from src.fastapi_mongo_base.errors.base import BaseHTTPException
from src.fastapi_mongo_base.errors.responses import (
    APIErrorResponseModel,
    ValidationErrorResponseModel,
)

from .app.server import app as fastapi_app


def test_openapi_documents_error_schemas() -> None:
    """OpenAPI should document custom error response schemas."""
    schema = fastapi_app.openapi()

    assert "APIErrorResponseModel" in schema["components"]["schemas"]
    assert "ValidationErrorResponseModel" in schema["components"]["schemas"]

    list_get = schema["paths"]["/test"]["get"]["responses"]
    assert "404" in list_get
    assert (
        list_get["404"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/APIErrorResponseModel"
    )

    create_post = schema["paths"]["/test"]["post"]["responses"]
    assert "422" in create_post
    assert (
        create_post["422"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ValidationErrorResponseModel"
    )


def test_openapi_error_models_match_handler_output() -> None:
    """Documented schemas should include fields returned by handlers."""
    api_schema = APIErrorResponseModel.model_json_schema()
    assert "message" in api_schema["properties"]
    assert "error_code" in api_schema["properties"]
    assert "detail" in api_schema["properties"]

    validation_schema = ValidationErrorResponseModel.model_json_schema()
    assert "reasons" in validation_schema["properties"]
    assert validation_schema["properties"]["error_code"]["default"] == (
        "validation_error"
    )


def test_runtime_validation_error_matches_openapi_schema() -> None:
    """Validation handler response should match documented error shape."""
    client = TestClient(fastapi_app)
    response = client.post("/test", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_error"
    assert "message" in body
    assert "reasons" in body
    assert isinstance(body["reasons"], list)


def test_runtime_base_http_exception_matches_openapi_schema() -> None:
    """BaseHTTPException handler response should match documented shape."""
    from starlette.requests import Request

    from fastapi_mongo_base.core.exceptions import base_http_exception_handler

    request = Request({
        "type": "http",
        "headers": [],
        "method": "GET",
        "path": "/test/not-a-real-uid",
    })
    exc = BaseHTTPException(
        status_code=404,
        error_code="item_not_found",
        message={"en": "Testentity not found"},
    )

    response = base_http_exception_handler(request, exc)
    body = response.body.decode()

    assert response.status_code == 404
    assert "item_not_found" in body
    assert "Testentity not found" in body


def test_custom_route_documents_api_error_response() -> None:
    """App-level responses should document APIErrorResponseModel on routes."""
    from fastapi import FastAPI

    from src.fastapi_mongo_base.core.app_factory import (
        setup_exception_handlers,
    )
    from src.fastapi_mongo_base.errors.responses import (
        COMMON_ERROR_RESPONSES,
        setup_openapi_errors,
    )

    app = FastAPI(responses=COMMON_ERROR_RESPONSES)
    setup_exception_handlers(app=app)
    setup_openapi_errors(app)

    @app.get("/missing")
    def raise_not_found() -> None:
        raise BaseHTTPException(
            status_code=404,
            error_code="item_not_found",
            message={"en": "Item not found"},
        )

    schema = app.openapi()
    responses = schema["paths"]["/missing"]["get"]["responses"]
    assert (
        responses["404"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/APIErrorResponseModel"
    )
