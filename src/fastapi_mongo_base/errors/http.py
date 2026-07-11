"""Structured HTTP API error exceptions."""

from .base import BaseHTTPException


class ServerError(BaseHTTPException):
    """Base exception for application API errors."""

    status_code: int = 500
    error_code: str = "internal_server_error"
    message_en: str = "Internal server error"
    message_fa: str | None = "خطای داخلی سرور رخ داده است"

    def __init__(
        self,
        error_code: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize ServerError with optional detail and data."""
        super().__init__(
            status_code=self.status_code,
            error_code=error_code or self.error_code,
            detail=detail or self.message_en,
            message=message,
            **kwargs,
        )


class BadRequestError(BaseHTTPException):
    """Raised when a request is invalid."""

    status_code = 400
    error_code = "bad_request"
    message_en = "Bad request"
    message_fa = "درخواست نامعتبر"


class UnauthorizedError(BaseHTTPException):
    """Raised when a request is unauthorized."""

    status_code = 401
    error_code = "unauthorized"
    message_en = "Unauthorized"
    message_fa = "دسترسی غیر مجاز"


class ForbiddenError(BaseHTTPException):
    """Raised when a request is forbidden."""

    status_code = 403
    error_code = "permission_denied"
    message_en = "Permission denied"
    message_fa = "دسترسی غیر مجاز"


class NotFoundError(BaseHTTPException):
    """Raised when a requested entity is not found."""

    status_code = 404
    error_code = "resource_not_found"
    message_en = "Resource not found"
    message_fa = "یافت نشد"


class AlreadyExistsError(BaseHTTPException):
    """Raised when an entity already exists."""

    status_code = 409
    error_code = "resource_already_exists"
    message_en = "Resource already exists"
    message_fa = "نمونه‌ی مشابه وجود دارد"


class ConflictError(BaseHTTPException):
    """Raised when a request conflicts with current state."""

    status_code = 409
    error_code = "resource_conflict"
    message_en = "Resource conflict"
    message_fa = "اطلاعات ارسال شده تداخل دارد"


class PaymentRequiredError(BaseHTTPException):
    """Raised when payment is required before access."""

    status_code = 402
    error_code = "resource_payment_required"
    message_en = "Resource payment required"
    message_fa = "برای دسترسی، پرداخت لازم است"


class GoneError(BaseHTTPException):
    """Raised when an entity is no longer available."""

    status_code = 410
    error_code = "resource_gone"
    message_en = "Resource gone"
    message_fa = "در دسترس نیست"


class LockedError(BaseHTTPException):
    """Raised when an entity is locked."""

    status_code = 423
    error_code = "resource_locked"
    message_en = "Resource locked"
    message_fa = "قفل شده است"
