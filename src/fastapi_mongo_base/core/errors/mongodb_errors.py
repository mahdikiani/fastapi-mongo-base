"""MongoDB error types and PyMongo-to-HTTP exception conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi_mongo_base.core.errors.resource_errors import (
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
)
from fastapi_mongo_base.core.exceptions import BaseHTTPException

if TYPE_CHECKING:
    from pymongo.errors import PyMongoError


class MongoDBError(BaseHTTPException):
    """Base exception for all MongoDB errors."""

    status_code: int = 500
    error_code: str = "db_error"
    message_en: str = "A database error occurred"
    message_fa: str | None = "یک خطای پایگاه داده رخ داده است"

    def __init__(
        self,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize MongoDBError with optional detail, message, and data."""
        super().__init__(
            status_code=self.status_code,
            error_code=self.error_code,
            detail=detail or self.message_en,
            message=message,
            **kwargs,
        )


class MongoDBConnectionError(MongoDBError):
    """Raised when a MongoDB connection error occurs."""

    status_code = 503
    error_code = "mongodb_connection_error"
    message_en = "A MongoDB connection error occurred"
    message_fa = (
        "در حال حاضر امکان اتصال به پایگاه داده وجود ندارد. "
        "لطفاً چند لحظه دیگر دوباره تلاش کنید."
    )


class MongoDBTimeoutError(MongoDBError):
    """Raised when a MongoDB network timeout error occurs."""

    status_code = 504
    error_code = "mongodb_timeout_error"
    message_en = "A MongoDB timeout error occurred"
    message_fa = "یک خطای timeout پایگاه داده رخ داده است"


class MongodbOperationTimeoutError(MongoDBError):
    """Raised when a MongoDB operation timeout error occurs."""

    status_code = 504
    error_code = "mongodb_operation_timeout_error"
    message_en = "A MongoDB operation timeout error occurred"
    message_fa = "یک خطای timeout عملیات پایگاه داده رخ داده است"


class DocumentNotFoundError(MongoDBError, ResourceNotFoundError):
    """Raised when a document is not found."""

    status_code = 404
    error_code = "document_not_found"
    message_en = "Document not found"
    message_fa = "سند یافت نشد"


class DocumentAlreadyExistsError(MongoDBError, ResourceAlreadyExistsError):
    """Raised when a document already exists."""

    status_code = 409
    error_code = "document_already_exists"
    message_en = "Document already exists"
    message_fa = "سند قبلاً وجود دارد"


class DocumentDuplicateKeyError(MongoDBError):
    """Raised when a duplicate key constraint is violated."""

    status_code = 409
    error_code = "document_duplicate_key"
    message_en = "Document with this key already exists"
    message_fa = "سند با این کلید قبلاً وجود دارد"


class MultipleDocumentsFoundError(MongoDBError):
    """Raised when a query expected one document but found several."""

    status_code = 409
    error_code = "multiple_documents_found"
    message_en = "Multiple documents found"
    message_fa = "چندین سند یافت شد"


def find_pymongo_error(exc: BaseException) -> PyMongoError | None:
    """
    Walk the exception chain and return the first PyMongoError.

    Checks ``__cause__`` first, then ``__context__`` (unless suppressed).
    """
    try:
        from pymongo.errors import PyMongoError
    except ImportError:
        return None

    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, PyMongoError):
            return current

        if current.__cause__ is not None:
            current = current.__cause__
            continue

        if (
            current.__context__ is not None
            and not current.__suppress_context__
        ):
            current = current.__context__
            continue

        break

    return None


def convert_pymongo_error(exc: PyMongoError) -> MongoDBError:
    """Map a PyMongoError to the appropriate MongoDB HTTP exception."""
    from pymongo.errors import (
        AutoReconnect,
        ConnectionFailure,
        DuplicateKeyError,
        ExecutionTimeout,
        NetworkTimeout,
        NotPrimaryError,
        OperationFailure,
        ServerSelectionTimeoutError,
        WaitQueueTimeoutError,
        WTimeoutError,
    )

    detail = str(exc)

    if isinstance(exc, DuplicateKeyError):
        return DocumentDuplicateKeyError(detail=detail)

    if (
        isinstance(exc, OperationFailure)
        and getattr(exc, "code", None) == 11000
    ):
        return DocumentDuplicateKeyError(detail=detail)

    if isinstance(exc, NetworkTimeout):
        return MongoDBTimeoutError(detail=detail)

    if isinstance(exc, (ExecutionTimeout, WTimeoutError)):
        return MongodbOperationTimeoutError(detail=detail)

    if isinstance(
        exc,
        (
            ServerSelectionTimeoutError,
            ConnectionFailure,
            AutoReconnect,
            NotPrimaryError,
            WaitQueueTimeoutError,
        ),
    ):
        return MongoDBConnectionError(detail=detail)

    return MongoDBError(detail=detail)
