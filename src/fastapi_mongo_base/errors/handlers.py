"""Exception handlers for FastAPI applications."""

import json
import logging
import traceback

import json_advanced
from fastapi import Request
from fastapi.exceptions import (
    RequestValidationError,
    ResponseValidationError,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..i18n import (
    VALIDATION_ERROR_MESSAGE,
    select_request_messages,
)
from .base import BaseHTTPException
from .mongodb import (
    convert_pymongo_error,
    find_pymongo_error,
)
from .responses import (
    APIErrorResponseModel,
    InternalErrorResponseModel,
    ValidationErrorResponseModel,
    ValidationReason,
)

error_messages = {}


def base_http_exception_handler(
    request: Request, exc: BaseHTTPException
) -> JSONResponse:
    """
    Handle BaseHTTPException and return JSON response.

    Args:
        request: FastAPI request object.
        exc: BaseHTTPException instance.

    Returns:
        JSONResponse with error details.

    """
    logging.debug("base_http_exception_handler: %s\n%s", request.url, exc)

    message = select_request_messages(request, exc.message)

    content = APIErrorResponseModel(
        message=message,
        error_code=exc.error_code,
        detail=exc.detail,
        **exc.data,
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=content)


def _resolve_validation_message(request: Request) -> dict[str, str]:
    return select_request_messages(request, VALIDATION_ERROR_MESSAGE)


def _format_validation_reasons(errors: list[dict]) -> list[dict]:
    reasons_by_field: dict[str, dict] = {}
    for error in json.loads(json_advanced.dumps(errors)):
        loc = error.pop("loc", ())
        field = str(loc[-1]) if loc else "unknown"
        error.pop("url", None)
        error["field"] = field
        reasons_by_field.setdefault(field, error)
    return list(reasons_by_field.values())


def _validation_error_response(
    request: Request,
    errors: list[dict],
    status_code: int,
) -> JSONResponse:
    content = ValidationErrorResponseModel(
        message=_resolve_validation_message(request),
        reasons=[
            ValidationReason(**reason)
            for reason in _format_validation_reasons(errors)
        ],
    ).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=content)


def pydantic_exception_handler(
    request: Request, exc: RequestValidationError | ResponseValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors and return JSON response.

    Args:
        request: FastAPI request object.
        exc: RequestValidationError or ResponseValidationError instance.

    Returns:
        JSONResponse with validation error details.

    """
    logging.debug("pydantic_exception_handler: %s\n%s", request.url, exc)

    status_code = 500 if isinstance(exc, ResponseValidationError) else 422
    return _validation_error_response(request, exc.errors(), status_code)


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle FastAPI request validation errors with body preview.

    Args:
        request: FastAPI request object.
        exc: RequestValidationError instance.

    Returns:
        JSONResponse with validation error details.

    """
    body_preview = b"<no body available>"

    if hasattr(request.state, "raw_body"):
        body_preview = request.state.raw_body[:100]
    else:
        try:
            body_preview = (await request.body())[:100]
        except RuntimeError:
            body_preview = b"<stream consumed>"

    logging.error(
        "request_validation_exception: %s %s\n"
        "Body preview: %s\nValidation errors: %s\nHeaders: %s",
        request.url,
        exc,
        body_preview,
        exc.errors(),
        dict(request.headers),
    )

    return _validation_error_response(request, exc.errors(), 422)


def mongodb_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle PyMongo errors and return a structured JSON response.

    Args:
        request: FastAPI request object.
        exc: PyMongoError instance (or subclass).

    Returns:
        JSONResponse with MongoDB error details.

    """
    logging.error("MongoDB error on %s: %s", request.url, exc)
    return base_http_exception_handler(request, convert_pymongo_error(exc))


def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle general exceptions and return JSON response.

    Args:
        request: FastAPI request object.
        exc: Exception instance.

    Returns:
        JSONResponse with error message.

    """
    traceback_str = "".join(traceback.format_tb(exc.__traceback__))
    logging.error("Exception: %s %s", traceback_str, exc)
    logging.error("Exception on request: %s", request.url)

    pymongo_exc = find_pymongo_error(exc)
    if pymongo_exc is not None:
        logging.error("MongoDB error (from exception chain): %s", pymongo_exc)
        return base_http_exception_handler(
            request, convert_pymongo_error(pymongo_exc)
        )

    try:
        from redis.exceptions import RedisError

        if isinstance(exc, RedisError):
            logging.exception("Redis error on %s", request.url)
            content = InternalErrorResponseModel(
                message="A Redis error occurred",
            ).model_dump(mode="json")
            return JSONResponse(status_code=503, content=content)
    except ImportError:
        pass

    content = InternalErrorResponseModel(message=str(exc)).model_dump(
        mode="json"
    )
    return JSONResponse(status_code=500, content=content)


EXCEPTION_HANDLERS = {
    BaseHTTPException: base_http_exception_handler,
    ValidationError: pydantic_exception_handler,
    ResponseValidationError: pydantic_exception_handler,
    RequestValidationError: request_validation_exception_handler,
    Exception: general_exception_handler,
}

try:
    from pymongo.errors import PyMongoError

    EXCEPTION_HANDLERS[PyMongoError] = mongodb_exception_handler
except ImportError:
    pass


try:
    from usso.integrations.fastapi import (
        EXCEPTION_HANDLERS as USSO_EXCEPTION_HANDLERS,
    )

    EXCEPTION_HANDLERS.update(USSO_EXCEPTION_HANDLERS)
except ImportError:
    pass
