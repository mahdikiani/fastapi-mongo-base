"""Exception handlers and custom HTTP exceptions for FastAPI."""

import json
import logging
import os
import traceback
from typing import TYPE_CHECKING

import json_advanced
from fastapi import Request
from fastapi.exceptions import (
    HTTPException,
    RequestValidationError,
    ResponseValidationError,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from fastapi_mongo_base.core.errors.i18n import (
    build_messages,
    http_error_content,
    normalize_messages,
    resolve_detail,
)

if TYPE_CHECKING:
    from fastapi_mongo_base.core.errors.db_errors import MongoDBError
    from fastapi_mongo_base.core.errors.resource_errors import ResourceError

try:
    from usso.integrations.fastapi import (
        EXCEPTION_HANDLERS as usso_exception_handler,  # noqa: N811
    )
except ImportError:
    usso_exception_handler = {}

error_messages: dict[str, str | dict[str, str]] = {}


class BaseHTTPException(HTTPException):
    """
    Base HTTP exception with multi-language message support.

    Attributes:
        status_code: HTTP status code.
        error: Error code string.
        message: Dictionary of language-specific error messages.
        detail: Error detail string.
        data: Additional error data.

    """

    def __init__(
        self,
        status_code: int,
        error: str,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """
        Initialize base HTTP exception.

        Args:
            status_code: HTTP status code.
            error: Error code string.
            detail: Optional error detail message.
            message: Optional dictionary of language-specific messages.
            **kwargs: Additional error data.

        """
        self.status_code = status_code
        self.error = error
        if message is None:
            if detail:
                msg = build_messages(detail)
            else:
                msg = normalize_messages(
                    error_messages.get(error),
                    fallback=error if isinstance(error, str) else str(error),
                )
        else:
            msg = dict(message)

        self.message = msg
        self.detail = resolve_detail(message=msg, detail=detail)
        self.data = kwargs
        super().__init__(status_code, detail=self.detail)


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
    return JSONResponse(
        status_code=exc.status_code,
        content=http_error_content(
            request,
            message=exc.message,
            error=exc.error,
            detail=exc.detail,
            data=exc.data,
        ),
    )


def mongodb_error_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle MongoDBError subclasses and map driver errors to structured JSON.

    FastAPI matches this handler via MRO for MongoDBError subclasses.
    pymongo_exception_handler and general_exception_handler delegate here
    after resolving the exception (including __cause__ / __context__ chains).

    Args:
        request: FastAPI request object.
        exc: MongoDBError, pymongo/BSON driver error, or wrapped driver error.

    Returns:
        JSONResponse with error details and any context from exc.data.

    """
    from fastapi_mongo_base.core.errors.db_errors import (
        MongoDBError,
        from_any_exception,
        from_pymongo_error,
    )

    if isinstance(exc, MongoDBError):
        mongo_exc = exc
    elif (resolved := from_any_exception(exc)) is not None:
        mongo_exc = resolved
    else:
        mongo_exc = from_pymongo_error(exc)

    log_level = (
        logging.ERROR if mongo_exc.status_code >= 500 else logging.WARNING
    )
    logging.log(
        log_level,
        "mongodb_error_handler: %s [%s] %s - %s data=%s",
        request.url,
        mongo_exc.error,
        type(mongo_exc).__name__,
        mongo_exc.detail,
        mongo_exc.data,
        exc_info=(type(exc), exc, exc.__traceback__)
        if not isinstance(exc, MongoDBError)
        else False,
    )
    return JSONResponse(
        status_code=mongo_exc.status_code,
        content=http_error_content(
            request,
            message=mongo_exc.message,
            error=mongo_exc.error,
            detail=mongo_exc.detail,
            data=mongo_exc.data,
        ),
    )


def resource_error_handler(
    request: Request, exc: "ResourceError"
) -> JSONResponse:
    """
    Handle ResourceError and all subclasses.

    Registered on the ResourceError base class so every resource-specific
    exception (ResourceNotFoundError, ResourceForbiddenError, etc.) is
    handled here before the generic BaseHTTPException handler.

    Args:
        request: FastAPI request object.
        exc: ResourceError instance or subclass.

    Returns:
        JSONResponse with error details and any context from exc.data.

    """
    log_level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    logging.log(
        log_level,
        "resource_error_handler: %s [%s] %s - %s data=%s",
        request.url,
        exc.error,
        type(exc).__name__,
        exc.detail,
        exc.data,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=http_error_content(
            request,
            message=exc.message,
            error=exc.error,
            detail=exc.detail,
            data=exc.data,
        ),
    )


def pydantic_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors and return JSON response.

    Args:
        request: FastAPI request object.
        exc: ValidationError instance.

    Returns:
        JSONResponse with validation error details.

    """
    logging.debug("pydantic_exception_handler: %s\n%s", request.url, exc)
    return JSONResponse(
        status_code=500,
        content={
            "message": str(exc),
            "error": "Exception",
            "errors": json.loads(json_advanced.dumps(exc.errors())),
        },
    )


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
    # Try to get request body from different sources
    body_preview = b"<no body available>"

    # First try to get from request state (if BodyCaptureMiddleware is used)
    if hasattr(request.state, "raw_body"):
        body_preview = request.state.raw_body[:100]
    else:
        # Fallback: try to read from request (might fail if stream consumed)
        try:
            body_preview = (await request.body())[:100]
        except RuntimeError:
            # Stream already consumed, likely during validation
            body_preview = b"<stream consumed>"

    # Log detailed information about the validation error
    logging.error(
        "request_validation_exception: %s %s\n"
        "Body preview: %s\nValidation errors: %s\nHeaders: %s",
        request.url,
        exc,
        body_preview,
        exc.errors(),
        dict(request.headers),
    )

    from fastapi.exception_handlers import (
        request_validation_exception_handler as default_handler,
    )

    return await default_handler(request, exc)


def general_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle general exceptions and return JSON response.

    Unwraps pymongo/BSON errors hidden in __cause__ / __context__ chains
    before falling back to a generic 500 response.

    Args:
        request: FastAPI request object.
        exc: Exception instance.

    Returns:
        JSONResponse with error message.

    """
    from fastapi_mongo_base.core.errors.db_errors import from_any_exception

    mongo_exc = from_any_exception(exc)
    if mongo_exc is not None:
        return mongodb_error_handler(request, exc)

    traceback_str = "".join(traceback.format_tb(exc.__traceback__))
    logging.error("Exception: %s %s", traceback_str, exc)
    logging.error("Exception on request: %s", request.url)

    try:
        from redis.exceptions import RedisError

        if isinstance(exc, RedisError):
            logging.error("Redis error")
            os._exit(1)
    except ImportError:
        pass

    return JSONResponse(
        status_code=500,
        content={"message": str(exc), "error": "Exception"},
    )


from fastapi_mongo_base.core.errors.db_errors import MongoDBError
from fastapi_mongo_base.core.errors.resource_errors import ResourceError

try:
    from pymongo.errors import PyMongoError as _PyMongoError
except ImportError:
    _PyMongoError = None


def pymongo_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Handle raw pymongo/BSON driver exceptions matched via MRO.

    Delegates to mongodb_error_handler which maps the driver error to a
    MongoDBError subclass.

    Args:
        request: FastAPI request object.
        exc: PyMongoError or BSON InvalidId from the driver.

    Returns:
        JSONResponse with mapped database error details.

    """
    return mongodb_error_handler(request, exc)


# A dictionary for dynamic registration
EXCEPTION_HANDLERS = {
    MongoDBError: mongodb_error_handler,
    ResourceError: resource_error_handler,
    BaseHTTPException: base_http_exception_handler,
    ValidationError: pydantic_exception_handler,
    ResponseValidationError: pydantic_exception_handler,
    RequestValidationError: request_validation_exception_handler,
    Exception: general_exception_handler,
}

if _PyMongoError is not None:
    EXCEPTION_HANDLERS[_PyMongoError] = pymongo_exception_handler

try:
    from bson.errors import InvalidId as _BsonInvalidId

    EXCEPTION_HANDLERS[_BsonInvalidId] = pymongo_exception_handler
except ImportError:
    pass

EXCEPTION_HANDLERS.update(usso_exception_handler)
