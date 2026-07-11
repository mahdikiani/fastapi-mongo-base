"""HTTP status-code API error exceptions."""

from .base import BaseHTTPException


class BadRequestError(BaseHTTPException):
    """Raised when a request is invalid."""

    status_code = 400
    error_code = "bad_request"
    message_en = "Bad request"
    message_fa = "درخواست نامعتبر"


try:
    from usso.exceptions import PermissionDenied as _USSOPermissionDenied
    from usso.exceptions import USSOException as _USSOException

    class UnauthorizedError(BaseHTTPException, _USSOException):
        """Raised when a request is unauthorized (when USSO is installed)."""

        status_code = 401
        error_code = "unauthorized"
        message_en = "Unauthorized"
        message_fa = "لطفا وارد حساب کاربری خود شوید."

        def __init__(
            self,
            error_code: str | None = None,
            detail: str | None = None,
            message: dict | None = None,
            **kwargs: object,
        ) -> None:
            """Initialize with package HTTP error fields (USSO-compatible)."""
            BaseHTTPException.__init__(
                self,
                status_code=self.status_code,
                error_code=error_code or self.error_code,
                detail=detail,
                message=message,
                **kwargs,
            )

    class ForbiddenError(BaseHTTPException, _USSOPermissionDenied):
        """Raised when a request is forbidden (when USSO is installed)."""

        status_code = 403
        error_code = "permission_denied"
        message_en = "Permission denied"
        message_fa = "دسترسی غیر مجاز"

        def __init__(
            self,
            error_code: str | None = None,
            detail: str | None = None,
            message: dict | None = None,
            **kwargs: object,
        ) -> None:
            """Initialize with package HTTP error fields (USSO-compatible)."""
            BaseHTTPException.__init__(
                self,
                status_code=self.status_code,
                error_code=error_code or self.error_code,
                detail=detail,
                message=message,
                **kwargs,
            )

except ImportError:

    class UnauthorizedError(BaseHTTPException):
        """Raised when a request is unauthorized."""

        status_code = 401
        error_code = "unauthorized"
        message_en = "Unauthorized"
        message_fa = "لطفا وارد حساب کاربری خود شوید."

    class ForbiddenError(BaseHTTPException):
        """Raised when a request is forbidden."""

        status_code = 403
        error_code = "permission_denied"
        message_en = "Permission denied"
        message_fa = "دسترسی غیر مجاز"


class PaymentRequiredError(BaseHTTPException):
    """Raised when payment is required before access."""

    status_code = 402
    error_code = "resource_payment_required"
    message_en = "Resource payment required"
    message_fa = "برای دسترسی، پرداخت لازم است"


class NotFoundError(BaseHTTPException):
    """Raised when a requested entity is not found."""

    status_code = 404
    error_code = "resource_not_found"
    message_en = "Resource not found"
    message_fa = "نمونه یافت نشد"


class MethodNotAllowedError(BaseHTTPException):
    """Raised when a request method is not allowed."""

    status_code = 405
    error_code = "method_not_allowed"
    message_en = "Method not allowed"
    message_fa = "متد درخواستی مجاز نیست"


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


class GoneError(BaseHTTPException):
    """Raised when an entity is no longer available."""

    status_code = 410
    error_code = "resource_gone"
    message_en = "Resource gone"
    message_fa = "در دسترس نیست"


class PreconditionFailedError(BaseHTTPException):
    """Raised when a precondition failed."""

    status_code = 412
    error_code = "precondition_failed"
    message_en = "Precondition failed"
    message_fa = "پیش‌شرط نقض شده است"


class TeaPotError(BaseHTTPException):
    """Raised when a request is a teapot."""

    status_code = 418
    error_code = "teapot"
    message_en = "I'm a teapot"
    message_fa = "من نمی‌خواهم پاسخ بدهم!"


class LockedError(BaseHTTPException):
    """Raised when an entity is locked."""

    status_code = 423
    error_code = "resource_locked"
    message_en = "Resource locked"
    message_fa = "قفل شده است"


class TooManyRequestsError(BaseHTTPException):
    """Raised when a request is made too many times."""

    status_code = 429
    error_code = "too_many_requests"
    message_en = "Too many requests"
    message_fa = "درخواست‌های همزمان زیادی ارسال شده است."


class ServerError(BaseHTTPException):
    """Base exception for application API errors."""

    status_code: int = 500
    error_code: str = "internal_server_error"
    message_en: str = "Internal server error"
    message_fa: str | None = "خطای داخلی سرور رخ داده است"


class FeatureNotImplementedError(BaseHTTPException):
    """Raised when a requested feature is not implemented (HTTP 501)."""

    status_code = 501
    error_code = "not_implemented"
    message_en = "Not implemented"
    message_fa = "این قابلیت هنوز فعال نشده است."


class ServiceUnavailableError(BaseHTTPException):
    """Raised when a service is unavailable."""

    status_code = 503
    error_code = "service_unavailable"
    message_en = "Service unavailable"
    message_fa = "سرویس در دسترس نیست."


class GatewayTimeoutError(BaseHTTPException):
    """Raised when a request times out."""

    status_code = 504
    error_code = "gateway_timeout"
    message_en = "Gateway timeout"
    message_fa = "درگاه در دسترس نیست."
