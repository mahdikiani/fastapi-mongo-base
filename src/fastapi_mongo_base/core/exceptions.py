"""Exception handlers and custom HTTP exceptions for FastAPI."""

import json
import logging
import os
import traceback

import json_advanced
from fastapi import Request
from fastapi.exceptions import (
    HTTPException,
    RequestValidationError,
    ResponseValidationError,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

try:
    from usso.integrations.fastapi import (
        EXCEPTION_HANDLERS as usso_exception_handler,  # noqa: N811
    )
except ImportError:
    usso_exception_handler = {}

error_messages = {}


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

    status_code: int = 500
    error_code: str = "unknown_error"
    message_en: str = "An unknown error occurred"
    message_fa: str | None = "یک خطای ناشناخته رخ داده است"

    def __init__(
        self,
        status_code: int,
        error_code: str,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """
        Initialize base HTTP exception.

        Args:
            status_code: HTTP status code.
            error_code: Error code string.
            detail: Optional error detail message.
            message: Optional dictionary of language-specific messages.
            **kwargs: Additional error data.

        """
        self.status_code = status_code
        self.error_code = error_code
        if message is None:
            if self.message_en and self.message_fa:
                self.message = {
                    "en": self.message_en,
                    "fa": self.message_fa,
                }
            else:
                self.message = {
                    "en": detail,
                }
        self.detail = detail or str(self.message.get("en"))
        self.data = kwargs
        super().__init__(status_code, detail=detail)


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

    if request.headers.get("accept-language"):
        locale = request.headers.get("accept-language").split(",")[0]
        message = {locale: exc.message.get(locale)}
    else:
        message = exc.message

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": message,
            "error": exc.error_code,
            "detail": exc.detail,
            **exc.data,
        },
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
    from fastapi_mongo_base.core.errors.mongodb_errors import (
        convert_pymongo_error,
    )

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

    from fastapi_mongo_base.core.errors.mongodb_errors import (
        convert_pymongo_error,
        find_pymongo_error,
    )

    pymongo_exc = find_pymongo_error(exc)
    if pymongo_exc is not None:
        logging.error("MongoDB error (from exception chain): %s", pymongo_exc)
        return base_http_exception_handler(
            request, convert_pymongo_error(pymongo_exc)
        )

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


# A dictionary for dynamic registration
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

EXCEPTION_HANDLERS.update(usso_exception_handler)
