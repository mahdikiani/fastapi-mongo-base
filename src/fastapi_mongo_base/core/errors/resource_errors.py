"""Resource error exceptions for HTTP responses."""

from fastapi_mongo_base.core.exceptions import BaseHTTPException


class ResourceError(BaseHTTPException):
    """Base exception for all resource errors."""

    status_code: int = 500
    error_code: str = "resource_error"
    message_en: str = "A resource error occurred"
    message_fa: str | None = "مشکلی در منبع پیش آمد. لطفاً دوباره تلاش کنید."

    def __init__(
        self,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize ResourceError with optional detail, message, and data."""
        super().__init__(
            status_code=self.status_code,
            error_code=self.error_code,
            detail=detail or self.message_en,
            message=message,
            **kwargs,
        )


class ResourceNotFoundError(ResourceError):
    """Raised when a resource is not found."""

    status_code = 404
    error_code = "resource_not_found"
    message_en = "Resource not found"
    message_fa = "یافت نشد"


class ResourceAlreadyExistsError(ResourceError):
    """Raised when a resource already exists."""

    status_code = 409
    error_code = "resource_already_exists"
    message_en = "Resource already exists"
    message_fa = "نمونه‌ی مشابه وجود دارد"


class ResourceConflictError(ResourceError):
    """Raised when a resource conflict occurs."""

    status_code = 409
    error_code = "resource_conflict"
    message_en = "Resource conflict"
    message_fa = "اطلاعات ارسال شده تداخل دارد"


class ResourcePaymentRequiredError(ResourceError):
    """Raised when a resource payment is required."""

    status_code = 402
    error_code = "resource_payment_required"
    message_en = "Resource payment required"
    message_fa = "برای دسترسی، پرداخت لازم است"


class ResourceForbiddenError(ResourceError):
    """Raised when a resource is forbidden."""

    status_code = 403
    error_code = "permission_denied"
    message_en = "Permission denied"
    message_fa = "دسترسی غیر مجاز"


class ResourceGoneError(ResourceError):
    """Raised when a resource is gone."""

    status_code = 410
    error_code = "resource_gone"
    message_en = "Resource gone"
    message_fa = "در دسترس نیست"


class ResourceLockedError(ResourceError):
    """Raised when a resource is locked."""

    status_code = 423
    error_code = "resource_locked"
    message_en = "Resource locked"
    message_fa = "قفل شده است"
