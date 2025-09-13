import json
import logging
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
    def __init__(
        self,
        status_code: int,
        error: str,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        self.status_code = status_code
        self.error = error
        msg: dict = {}
        if message is None:
            if detail:
                msg["en"] = detail
            else:
                msg["en"] = error_messages.get(error, error)
        else:
            msg = message

        self.message = msg
        self.detail = detail or str(self.message)
        self.data = kwargs
        super().__init__(status_code, detail=detail)


def base_http_exception_handler(
    request: Request, exc: BaseHTTPException
) -> JSONResponse:
    logging.debug("base_http_exception_handler: %s %s\n%s", request.url, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": exc.message,
            "error": exc.error,
            "detail": exc.detail,
            **exc.data,
        },
    )


def pydantic_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    logging.debug("pydantic_exception_handler: %s %s\n%s", request.url, exc)
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
    traceback_str = "".join(traceback.format_tb(exc.__traceback__))
    logging.error("Exception: %s %s", traceback_str, exc)
    logging.error("Exception on request: %s", request.url)
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

EXCEPTION_HANDLERS.update(usso_exception_handler)
