"""Tests for backward-compatible exception re-export modules."""

import src.fastapi_mongo_base.core.exceptions as core_exceptions
import src.fastapi_mongo_base.errors.exceptions as errors_exceptions
from src.fastapi_mongo_base.errors.base import BaseHTTPException
from src.fastapi_mongo_base.errors.handlers import EXCEPTION_HANDLERS


def test_core_exceptions_reexports_handlers() -> None:
    """core.exceptions exposes handler registry and base exception."""
    assert core_exceptions.BaseHTTPException is BaseHTTPException
    assert core_exceptions.EXCEPTION_HANDLERS is EXCEPTION_HANDLERS
    assert callable(core_exceptions.general_exception_handler)


def test_errors_exceptions_reexports_http_errors() -> None:
    """errors.exceptions exposes canonical HTTP error types."""
    assert errors_exceptions.ForbiddenError is not None
    assert issubclass(errors_exceptions.NotFoundError, BaseHTTPException)
