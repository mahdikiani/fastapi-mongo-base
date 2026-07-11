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


class NotFoundError(ServerError):
    """Raised when a requested entity is not found."""

    status_code = 404
    error_code = "resource_not_found"
    message_en = "Resource not found"
    message_fa = "یافت نشد"


class AlreadyExistsError(ServerError):
    """Raised when an entity already exists."""

    status_code = 409
    error_code = "resource_already_exists"
    message_en = "Resource already exists"
    message_fa = "نمونه‌ی مشابه وجود دارد"


class ConflictError(ServerError):
    """Raised when a request conflicts with current state."""

    status_code = 409
    error_code = "resource_conflict"
    message_en = "Resource conflict"
    message_fa = "اطلاعات ارسال شده تداخل دارد"


class PaymentRequiredError(ServerError):
    """Raised when payment is required before access."""

    status_code = 402
    error_code = "resource_payment_required"
    message_en = "Resource payment required"
    message_fa = "برای دسترسی، پرداخت لازم است"


class ForbiddenError(ServerError):
    """Raised when the caller lacks permission."""

    status_code = 403
    error_code = "permission_denied"
    message_en = "Permission denied"
    message_fa = "دسترسی غیر مجاز"


class GoneError(ServerError):
    """Raised when an entity is no longer available."""

    status_code = 410
    error_code = "resource_gone"
    message_en = "Resource gone"
    message_fa = "در دسترس نیست"


class LockedError(ServerError):
    """Raised when an entity is locked."""

    status_code = 423
    error_code = "resource_locked"
    message_en = "Resource locked"
    message_fa = "قفل شده است"


# Backward-compatible aliases from earlier refactors.
HTTPClientError = ServerError
APIError = ServerError
