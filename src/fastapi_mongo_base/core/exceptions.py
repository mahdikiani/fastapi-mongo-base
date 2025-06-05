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

error_messages = {}


class BaseHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        error: str,
        message: dict = None,
        detail: str = None,
        **kwargs,
    ):
        self.status_code = status_code
        self.error = error
        self.message = message
        if message is None:
            self.message = error_messages.get(error, error)
        if detail is None:
            detail = self.message
        self.detail = detail
        self.data = kwargs
        super().__init__(status_code, detail=detail)


async def base_http_exception_handler(
    request: Request, exc: BaseHTTPException
):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.message, "error": exc.error},
    )


async def pydantic_exception_handler(request: Request, exc: ValidationError):
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
):
    logging.error(
        f"request_validation_exception: {request.url} {exc}\n"
        f"{(await request.body())[:100]}"
    )
    from fastapi.exception_handlers import (
        request_validation_exception_handler as default_handler,
    )

    return await default_handler(request, exc)


async def general_exception_handler(request: Request, exc: Exception):
    traceback_str = "".join(traceback.format_tb(exc.__traceback__))
    logging.error(f"Exception: {traceback_str} {exc}")
    logging.error(f"Exception on request: {request.url}")
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
