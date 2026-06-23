"""MongoDB-related HTTP exceptions."""

from typing import ClassVar

from fastapi_mongo_base.core.errors.i18n import build_messages
from fastapi_mongo_base.core.exceptions import BaseHTTPException


class MongoDBError(BaseHTTPException):
    """Base exception for all MongoDB-related errors."""

    status_code: ClassVar[int] = 500
    error_code: ClassVar[str] = "mongodb_error"
    default_message: ClassVar[str] = "A database error occurred"
    default_message_fa: ClassVar[str | None] = (
        "مشکلی در پایگاه داده پیش آمد. لطفاً دوباره تلاش کنید."
    )

    def __init__(
        self,
        *,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(
            status_code=self.status_code,
            error=self.error_code,
            detail=detail,
            message=message
            or build_messages(self.default_message, self.default_message_fa),
            **kwargs,
        )


class MongoDBConnectionError(MongoDBError):
    """Raised when the application cannot establish a connection to MongoDB."""

    status_code = 503
    error_code = "mongodb_connection_error"
    default_message = "Unable to connect to the database"
    default_message_fa = (
        "در حال حاضر امکان اتصال به پایگاه داده وجود ندارد. "
        "لطفاً چند لحظه دیگر دوباره تلاش کنید."
    )


class MongoDBConnectionTimeoutError(MongoDBConnectionError):
    """Raised when a MongoDB connection attempt times out."""

    error_code = "mongodb_connection_timeout"
    default_message = "Database connection timed out"
    default_message_fa = (
        "اتصال به پایگاه داده بیش از حد طول کشید. لطفاً دوباره تلاش کنید."
    )


class MongoDBOperationTimeoutError(MongoDBError):
    """Raised when a MongoDB operation exceeds its time limit."""

    status_code = 504
    error_code = "mongodb_operation_timeout"
    default_message = "Database operation timed out"
    default_message_fa = (
        "انجام این درخواست بیش از حد طول کشید. لطفاً دوباره تلاش کنید."
    )


class DocumentNotFoundError(MongoDBError):
    """Raised when a requested document does not exist."""

    status_code = 404
    error_code = "document_not_found"
    default_message = "Document not found"
    default_message_fa = "موردی با این مشخصات پیدا نشد."

    def __init__(
        self,
        *,
        collection: str | None = None,
        uid: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if collection and uid:
                message = build_messages(
                    f"Document not found in '{collection}' with id '{uid}'",
                    f"در «{collection}» موردی با شناسه «{uid}» پیدا نشد.",
                )
            elif collection:
                message = build_messages(
                    f"Document not found in '{collection}'",
                    f"در «{collection}» موردی پیدا نشد.",
                )
            elif uid:
                message = build_messages(
                    f"Document with id '{uid}' not found",
                    f"موردی با شناسه «{uid}» پیدا نشد.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            collection=collection,
            uid=uid,
            **kwargs,
        )


class DocumentAlreadyExistsError(MongoDBError):
    """Raised when creating a document that already exists."""

    status_code = 409
    error_code = "document_already_exists"
    default_message = "Document already exists"
    default_message_fa = "این مورد از قبل ثبت شده است."

    def __init__(
        self,
        *,
        collection: str | None = None,
        uid: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if collection and uid:
                message = build_messages(
                    f"Document already exists in '{collection}' with id '{uid}'",
                    f"در «{collection}» موردی با شناسه «{uid}» از قبل ثبت شده است.",
                )
            elif collection:
                message = build_messages(
                    f"Document already exists in '{collection}'",
                    f"در «{collection}» این مورد از قبل وجود دارد.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            collection=collection,
            uid=uid,
            **kwargs,
        )


class DuplicateKeyError(MongoDBError):
    """Raised on unique-index constraint violations (MongoDB error code 11000)."""

    status_code = 409
    error_code = "duplicate_key"
    default_message = "A record with this value already exists"
    default_message_fa = (
        "این مقدار قبلاً ثبت شده است. لطفاً مقدار دیگری وارد کنید."
    )

    def __init__(
        self,
        *,
        field: str | None = None,
        value: str | None = None,
        collection: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if field and value:
                message = build_messages(
                    f"A record with {field}='{value}' already exists",
                    f"مقدار {field}='{value}' قبلاً ثبت شده است.",
                )
            elif field:
                message = build_messages(
                    f"A record with this {field} already exists",
                    f"این {field} قبلاً ثبت شده است. لطفاً مقدار دیگری وارد کنید.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            field=field,
            value=value,
            collection=collection,
            **kwargs,
        )


class MultipleDocumentsFoundError(MongoDBError):
    """Raised when a query expected a single document but found several."""

    status_code = 409
    error_code = "multiple_documents_found"
    default_message = "Multiple documents matched the query"
    default_message_fa = (
        "بیش از یک نتیجه پیدا شد. لطفاً جستجوی دقیق‌تری انجام دهید."
    )

    def __init__(
        self,
        *,
        collection: str | None = None,
        count: int | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if collection and count is not None:
                message = build_messages(
                    f"Expected a single document in '{collection}', "
                    f"but found {count}",
                    f"در «{collection}» باید یک نتیجه می‌یافت، "
                    f"اما {count} مورد پیدا شد.",
                )
            elif collection:
                message = build_messages(
                    f"Expected a single document in '{collection}', "
                    "but found multiple",
                    f"در «{collection}» باید یک نتیجه می‌یافت، "
                    "اما چند مورد پیدا شد.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            collection=collection,
            count=count,
            **kwargs,
        )


class DocumentValidationError(MongoDBError):
    """Raised when a document fails schema or field validation before save."""

    status_code = 422
    error_code = "document_validation_error"
    default_message = "Document validation failed"
    default_message_fa = "اطلاعات وارد شده معتبر نیست."

    def __init__(
        self,
        *,
        field: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if field and reason:
                message = build_messages(
                    f"Validation failed for field '{field}': {reason}",
                    f"مقدار «{field}» معتبر نیست: {reason}",
                )
            elif field:
                message = build_messages(
                    f"Validation failed for field '{field}'",
                    f"لطفاً مقدار «{field}» را بررسی و اصلاح کنید.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            field=field,
            reason=reason,
            **kwargs,
        )


class InvalidObjectIdError(MongoDBError):
    """Raised when an identifier is not a valid MongoDB ObjectId."""

    status_code = 400
    error_code = "invalid_object_id"
    default_message = "Invalid document identifier"
    default_message_fa = "شناسه وارد شده معتبر نیست."

    def __init__(
        self,
        *,
        value: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if value:
                message = build_messages(
                    f"Invalid document identifier: '{value}'",
                    f"شناسه «{value}» معتبر نیست. لطفاً شناسه را بررسی کنید.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            value=value,
            **kwargs,
        )


class InvalidQueryError(MongoDBError):
    """Raised when a query filter or aggregation pipeline is malformed."""

    status_code = 400
    error_code = "invalid_query"
    default_message = "Invalid database query"
    default_message_fa = "درخواست ارسالی معتبر نیست."

    def __init__(
        self,
        *,
        reason: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if reason:
                message = build_messages(reason, reason)
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            reason=reason,
            **kwargs,
        )


class MongoDBReadError(MongoDBError):
    """Raised when a read operation fails unexpectedly."""

    error_code = "mongodb_read_error"
    default_message = "Failed to read from the database"
    default_message_fa = (
        "خواندن اطلاعات با مشکل مواجه شد. لطفاً دوباره تلاش کنید."
    )


class MongoDBWriteError(MongoDBError):
    """Raised when a write operation fails unexpectedly."""

    error_code = "mongodb_write_error"
    default_message = "Failed to write to the database"
    default_message_fa = (
        "ذخیره اطلاعات با مشکل مواجه شد. لطفاً دوباره تلاش کنید."
    )


class BulkWriteError(MongoDBError):
    """Raised when a bulk write operation has one or more failures."""

    status_code = 400
    error_code = "bulk_write_error"
    default_message = "Bulk write operation failed"
    default_message_fa = (
        "ذخیره گروهی اطلاعات کامل نشد. لطفاً دوباره تلاش کنید."
    )

    def __init__(
        self,
        *,
        failed_count: int | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if failed_count is not None:
                message = build_messages(
                    f"Bulk write failed for {failed_count} document(s)",
                    f"ذخیره {failed_count} مورد با مشکل مواجه شد.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            failed_count=failed_count,
            **kwargs,
        )


class TransactionError(MongoDBError):
    """Raised when a multi-document transaction is aborted or cannot commit."""

    error_code = "transaction_error"
    default_message = "Database transaction failed"
    default_message_fa = (
        "این عملیات کامل نشد. لطفاً دوباره تلاش کنید."
    )


class WriteConflictError(MongoDBError):
    """Raised on optimistic-concurrency or write-conflict errors."""

    status_code = 409
    error_code = "write_conflict"
    default_message = (
        "The document was modified by another request. "
        "Please retry with the latest version"
    )
    default_message_fa = (
        "این مورد هم‌زمان توسط درخواست دیگری تغییر کرده است. "
        "لطفاً صفحه را به‌روزرسانی کنید و دوباره تلاش کنید."
    )


class UnauthorizedDatabaseAccessError(MongoDBError):
    """Raised when the database user lacks permission for the requested action."""

    status_code = 403
    error_code = "unauthorized_database_access"
    default_message = "Insufficient database permissions"
    default_message_fa = "شما دسترسی لازم برای این عملیات را ندارید."


class MongoDBIndexError(MongoDBError):
    """Raised when index creation or management fails."""

    error_code = "mongodb_index_error"
    default_message = "Database index operation failed"
    default_message_fa = (
        "مشکلی در به‌روزرسانی فهرست جستجو پیش آمد. لطفاً دوباره تلاش کنید."
    )

    def __init__(
        self,
        *,
        index: str | None = None,
        collection: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        if message is None:
            if collection and index:
                message = build_messages(
                    f"Failed to manage index '{index}' on collection '{collection}'",
                    f"به‌روزرسانی فهرست «{index}» در «{collection}» انجام نشد.",
                )
            elif index:
                message = build_messages(
                    f"Failed to manage index '{index}'",
                    f"به‌روزرسانی فهرست «{index}» انجام نشد.",
                )
            else:
                message = build_messages(
                    self.default_message,
                    self.default_message_fa,
                )
        super().__init__(
            detail=detail,
            message=message,
            index=index,
            collection=collection,
            **kwargs,
        )


def _duplicate_key_from_details(
    details: dict,
    *,
    detail: str | None = None,
) -> DuplicateKeyError:
    key_pattern = details.get("keyPattern") or {}
    key_value = details.get("keyValue") or {}
    field = next(iter(key_pattern), None)
    value = str(key_value[field]) if field and field in key_value else None
    return DuplicateKeyError(field=field, value=value, detail=detail)


def _map_connection_error(exc: Exception, detail: str) -> MongoDBError | None:
    from pymongo.errors import (
        ConfigurationError,
        ConnectionFailure,
        InvalidURI,
        NetworkTimeout,
        ServerSelectionTimeoutError,
        WaitQueueTimeoutError,
    )

    if isinstance(
        exc,
        (ServerSelectionTimeoutError, NetworkTimeout, WaitQueueTimeoutError),
    ):
        return MongoDBConnectionTimeoutError(detail=detail)
    if isinstance(exc, (ConnectionFailure, InvalidURI, ConfigurationError)):
        return MongoDBConnectionError(detail=detail)
    return None


def _map_write_error(exc: Exception, detail: str) -> MongoDBError | None:
    from pymongo.errors import (
        BulkWriteError as PyMongoBulkWriteError,
        DuplicateKeyError as PyMongoDuplicateKeyError,
        WriteConcernError,
        WriteError,
        WTimeoutError,
    )

    if isinstance(exc, PyMongoDuplicateKeyError):
        return _duplicate_key_from_details(
            getattr(exc, "details", {}) or {},
            detail=detail,
        )
    if isinstance(exc, PyMongoBulkWriteError):
        write_errors = (getattr(exc, "details", {}) or {}).get(
            "writeErrors", []
        )
        if len(write_errors) == 1 and write_errors[0].get("code") in (
            11000,
            11001,
        ):
            return _duplicate_key_from_details(write_errors[0], detail=detail)
        return BulkWriteError(
            failed_count=len(write_errors),
            detail=detail,
        )
    if isinstance(exc, WTimeoutError):
        return WriteConflictError(detail=detail)
    if isinstance(exc, WriteConcernError):
        return MongoDBWriteError(detail=detail)
    if isinstance(exc, WriteError):
        if getattr(exc, "code", None) in (11000, 11001):
            return _duplicate_key_from_details(
                getattr(exc, "details", {}) or {},
                detail=detail,
            )
        return MongoDBWriteError(detail=detail)
    return None


def _map_server_error_code(exc: Exception, detail: str) -> MongoDBError | None:
    from pymongo.errors import OperationFailure

    if not isinstance(exc, OperationFailure):
        return None

    code = getattr(exc, "code", None)
    if code in (13, 18):
        return UnauthorizedDatabaseAccessError(detail=detail, reason=detail)
    if code in (11000, 11001):
        return _duplicate_key_from_details(
            getattr(exc, "details", {}) or {},
            detail=detail,
        )
    if code == 112:
        return WriteConflictError(detail=detail)
    if code == 50:
        return MongoDBOperationTimeoutError(detail=detail)
    if code == 121:
        return DocumentValidationError(reason=detail, detail=detail)
    return MongoDBError(detail=detail)


def _map_operation_failure(exc: Exception, detail: str) -> MongoDBError | None:
    from pymongo.errors import (
        CursorNotFound,
        DocumentTooLarge,
        ExecutionTimeout,
        InvalidDocument,
        InvalidName,
        InvalidOperation,
    )

    if isinstance(exc, ExecutionTimeout):
        return MongoDBOperationTimeoutError(detail=detail)

    mapped = _map_server_error_code(exc, detail)
    if mapped is not None:
        return mapped

    if isinstance(exc, (InvalidDocument, DocumentTooLarge)):
        return DocumentValidationError(reason=detail, detail=detail)
    if isinstance(exc, (InvalidName, InvalidOperation)):
        return InvalidQueryError(reason=detail, detail=detail)
    if isinstance(exc, CursorNotFound):
        return MongoDBReadError(detail=detail)
    return None


def find_driver_error(
    exc: BaseException | None,
    *,
    _seen: set[int] | None = None,
) -> BaseException | None:
    """
    Find a pymongo or BSON driver error in exc or its cause/context chain.

    Returns None when exc is already a MongoDBError or no driver error exists.
    """
    if exc is None:
        return None
    if _seen is None:
        _seen = set()
    exc_id = id(exc)
    if exc_id in _seen:
        return None
    _seen.add(exc_id)

    if isinstance(exc, MongoDBError):
        return None

    try:
        from bson.errors import InvalidId

        if isinstance(exc, InvalidId):
            return exc
    except ImportError:
        pass

    try:
        from pymongo.errors import PyMongoError

        if isinstance(exc, PyMongoError):
            return exc
    except ImportError:
        pass

    for link in (exc.__cause__, exc.__context__):
        found = find_driver_error(link, _seen=_seen)
        if found is not None:
            return found
    return None


def from_any_exception(exc: Exception) -> MongoDBError | None:
    """
    Convert exc or a wrapped driver error into a MongoDBError subclass.

    Returns the exc unchanged when it is already MongoDBError, or None when
    exc is unrelated to MongoDB.
    """
    if isinstance(exc, MongoDBError):
        return exc
    driver = find_driver_error(exc)
    if driver is None:
        return None
    return from_pymongo_error(driver)


def from_pymongo_error(exc: Exception) -> MongoDBError:
    """
    Convert a pymongo/BSON driver error into a MongoDBError subclass.

    Check order matters: connection → write → operation failures.
    """
    detail = str(exc)

    try:
        from bson.errors import InvalidId

        if isinstance(exc, InvalidId):
            return InvalidObjectIdError(value=detail, detail=detail)
    except ImportError:
        pass

    try:
        from pymongo.errors import PyMongoError
    except ImportError:
        return MongoDBError(detail=detail)

    if not isinstance(exc, PyMongoError):
        return MongoDBError(detail=detail)

    for mapper in (
        _map_connection_error,
        _map_write_error,
        _map_operation_failure,
    ):
        mapped = mapper(exc, detail)
        if mapped is not None:
            return mapped

    return MongoDBError(detail=detail)


def raise_from_pymongo_error(exc: Exception) -> None:
    """Re-raise a driver error as MongoDBError, keeping the original traceback."""
    if isinstance(exc, MongoDBError):
        raise exc
    driver = find_driver_error(exc) or exc
    raise from_pymongo_error(driver) from exc
