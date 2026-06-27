"""Tests for MongoDB error conversion and exception handling."""

import pytest
from fastapi import Request
from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    DuplicateKeyError,
    ExecutionTimeout,
    NetworkTimeout,
    OperationFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
    WTimeoutError,
)

from fastapi_mongo_base.core.errors.mongodb_errors import (
    DocumentDuplicateKeyError,
    DocumentNotFoundError,
    MongoDBConnectionError,
    MongoDBError,
    MongodbOperationTimeoutError,
    MongoDBTimeoutError,
    convert_pymongo_error,
    find_pymongo_error,
)
from fastapi_mongo_base.core.exceptions import (
    general_exception_handler,
    mongodb_exception_handler,
)

MONGODB_ERROR_CASES = [
    pytest.param(
        MongoDBError,
        500,
        "db_error",
        "A database error occurred",
        "یک خطای پایگاه داده رخ داده است",
        id="MongoDBError",
    ),
    pytest.param(
        MongoDBConnectionError,
        503,
        "mongodb_connection_error",
        "A MongoDB connection error occurred",
        "در حال حاضر امکان اتصال به پایگاه داده وجود ندارد. "
        "لطفاً چند لحظه دیگر دوباره تلاش کنید.",
        id="MongoDBConnectionError",
    ),
    pytest.param(
        MongoDBTimeoutError,
        504,
        "mongodb_timeout_error",
        "A MongoDB timeout error occurred",
        "یک خطای timeout پایگاه داده رخ داده است",
        id="MongoDBTimeoutError",
    ),
    pytest.param(
        MongodbOperationTimeoutError,
        504,
        "mongodb_operation_timeout_error",
        "A MongoDB operation timeout error occurred",
        "یک خطای timeout عملیات پایگاه داده رخ داده است",
        id="MongodbOperationTimeoutError",
    ),
    pytest.param(
        DocumentNotFoundError,
        404,
        "document_not_found",
        "Document not found",
        "سند یافت نشد",
        id="DocumentNotFoundError",
    ),
    pytest.param(
        DocumentDuplicateKeyError,
        409,
        "document_duplicate_key",
        "Document with this key already exists",
        "سند با این کلید قبلاً وجود دارد",
        id="DocumentDuplicateKeyError",
    ),
]

CONVERT_CASES = [
    pytest.param(
        DuplicateKeyError("dup", 11000, {}),
        DocumentDuplicateKeyError,
        409,
        id="DuplicateKeyError",
    ),
    pytest.param(
        OperationFailure("dup key", code=11000),
        DocumentDuplicateKeyError,
        409,
        id="OperationFailure_11000",
    ),
    pytest.param(
        NetworkTimeout("network timeout"),
        MongoDBTimeoutError,
        504,
        id="NetworkTimeout",
    ),
    pytest.param(
        ExecutionTimeout("execution timeout"),
        MongodbOperationTimeoutError,
        504,
        id="ExecutionTimeout",
    ),
    pytest.param(
        WTimeoutError("write concern timeout"),
        MongodbOperationTimeoutError,
        504,
        id="WTimeoutError",
    ),
    pytest.param(
        ServerSelectionTimeoutError("server selection timeout"),
        MongoDBConnectionError,
        503,
        id="ServerSelectionTimeoutError",
    ),
    pytest.param(
        ConnectionFailure("connection failed"),
        MongoDBConnectionError,
        503,
        id="ConnectionFailure",
    ),
    pytest.param(
        AutoReconnect("auto reconnect"),
        MongoDBConnectionError,
        503,
        id="AutoReconnect",
    ),
    pytest.param(
        PyMongoError("generic db error"),
        MongoDBError,
        500,
        id="PyMongoError",
    ),
]


@pytest.mark.parametrize(
    ("exc_cls", "status_code", "error_code", "message_en", "message_fa"),
    MONGODB_ERROR_CASES,
)
def test_mongodb_error_class_messages(
    exc_cls: type[MongoDBError],
    status_code: int,
    error_code: str,
    message_en: str,
    message_fa: str,
) -> None:
    """Each MongoDB error defines the expected English and Farsi messages."""
    assert exc_cls.status_code == status_code
    assert exc_cls.error_code == error_code
    assert exc_cls.message_en == message_en
    assert exc_cls.message_fa == message_fa


@pytest.mark.parametrize(
    ("pymongo_exc", "expected_cls", "expected_status"),
    CONVERT_CASES,
)
def test_convert_pymongo_error(
    pymongo_exc: PyMongoError,
    expected_cls: type[MongoDBError],
    expected_status: int,
) -> None:
    """PyMongo errors are mapped to the correct MongoDB HTTP exception."""
    http_exc = convert_pymongo_error(pymongo_exc)

    assert isinstance(http_exc, expected_cls)
    assert http_exc.status_code == expected_status
    assert http_exc.detail == str(pymongo_exc)


def test_find_pymongo_error_direct() -> None:
    """find_pymongo_error returns a direct PyMongoError instance."""
    exc = DuplicateKeyError("dup", 11000, {})
    assert find_pymongo_error(exc) is exc


def test_find_pymongo_error_via_cause() -> None:
    """find_pymongo_error walks __cause__ to find a wrapped PyMongoError."""
    inner = DuplicateKeyError("dup", 11000, {})
    outer = RuntimeError("wrapped")
    outer.__cause__ = inner

    assert find_pymongo_error(outer) is inner


def _raise_runtime_error() -> None:
    raise RuntimeError("wrapped")


def test_find_pymongo_error_via_context() -> None:
    """find_pymongo_error walks __context__ when __cause__ is absent."""
    inner = DuplicateKeyError("dup", 11000, {})
    try:
        raise inner
    except DuplicateKeyError:
        try:
            _raise_runtime_error()
        except RuntimeError as caught:
            outer = caught
    assert find_pymongo_error(outer) is inner


def test_find_pymongo_error_returns_none_for_unrelated() -> None:
    """find_pymongo_error returns None when no PyMongoError is in the chain."""
    assert find_pymongo_error(ValueError("not mongo")) is None


def test_mongodb_exception_handler_returns_json() -> None:
    """mongodb_exception_handler returns a structured JSON error response."""
    request = Request({
        "type": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
    })
    pymongo_exc = DuplicateKeyError("dup", 11000, {})

    response = mongodb_exception_handler(request, pymongo_exc)
    body = response.body.decode()

    assert response.status_code == 409
    assert "document_duplicate_key" in body
    assert str(pymongo_exc) in body


def test_general_exception_handler_converts_chained_pymongo_error() -> None:
    """general_exception_handler converts chained PyMongo errors."""
    request = Request({
        "type": "http",
        "headers": [],
        "method": "GET",
        "path": "/",
    })
    inner = ServerSelectionTimeoutError("timeout")
    outer = RuntimeError("service failed")
    outer.__cause__ = inner

    response = general_exception_handler(request, outer)

    assert response.status_code == 503
    assert b"mongodb_connection_error" in response.body
