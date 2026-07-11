"""Backward-compatible re-exports for exception handlers."""

from ..errors.base import BaseHTTPException
from ..errors.handlers import (
    EXCEPTION_HANDLERS,
    base_http_exception_handler,
    error_messages,
    general_exception_handler,
    mongodb_exception_handler,
    pydantic_exception_handler,
    request_validation_exception_handler,
)

__all__ = [
    "EXCEPTION_HANDLERS",
    "BaseHTTPException",
    "base_http_exception_handler",
    "error_messages",
    "general_exception_handler",
    "mongodb_exception_handler",
    "pydantic_exception_handler",
    "request_validation_exception_handler",
]
