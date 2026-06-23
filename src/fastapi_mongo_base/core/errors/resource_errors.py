"""HTTP exceptions for API resources (entities, items, etc.)."""

from typing import ClassVar

from fastapi_mongo_base.core.errors.i18n import build_messages, class_messages
from fastapi_mongo_base.core.exceptions import BaseHTTPException


class ResourceError(BaseHTTPException):
    """Base exception for resource-related HTTP errors."""

    status_code: ClassVar[int] = 400
    error_code: ClassVar[str] = "resource_error"
    default_message: ClassVar[str] = "A resource error occurred"
    default_message_fa: ClassVar[str | None] = (
        "مشکلی در پردازش درخواست شما پیش آمد."
    )

    def __init__(
        self,
        *,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        message = class_messages(type(self), message)
        super().__init__(
            status_code=self.status_code,
            error=self.error_code,
            detail=detail,
            message=message,
            **kwargs,
        )


class ResourceNotFoundError(ResourceError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    error_code = "item_not_found"
    default_message = "Resource not found"
    default_message_fa = "موردی با این مشخصات پیدا نشد."

    def __init__(
        self,
        *,
        resource: str | None = None,
        uid: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and uid:
                message = build_messages(
                    f"{resource} with id '{uid}' not found",
                    f"{resource} با شناسه «{uid}» پیدا نشد.",
                )
            elif resource:
                message = build_messages(
                    f"{resource} not found",
                    f"{resource} پیدا نشد.",
                )
            elif uid:
                message = build_messages(
                    f"Resource with id '{uid}' not found",
                    f"موردی با شناسه «{uid}» پیدا نشد.",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            uid=uid,
            **kwargs,
        )


class ResourceAlreadyExistsError(ResourceError):
    """Raised when creating a resource that already exists."""

    status_code = 409
    error_code = "resource_already_exists"
    default_message = "Resource already exists"
    default_message_fa = "این مورد از قبل وجود دارد."

    def __init__(
        self,
        *,
        resource: str | None = None,
        uid: str | None = None,
        field: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and uid:
                message = build_messages(
                    f"{resource} with id '{uid}' already exists",
                    f"{resource} با شناسه «{uid}» از قبل ثبت شده است.",
                )
            elif resource and field:
                message = build_messages(
                    f"{resource} with this {field} already exists",
                    f"{resource} با این {field} از قبل ثبت شده است.",
                )
            elif resource:
                message = build_messages(
                    f"{resource} already exists",
                    f"{resource} از قبل وجود دارد.",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            uid=uid,
            field=field,
            **kwargs,
        )


class ResourcePaymentRequiredError(ResourceError):
    """Raised when payment is required to access the resource."""

    status_code = 402
    error_code = "payment_required"
    default_message = "Payment required"
    default_message_fa = "برای دسترسی به این بخش، پرداخت لازم است."

    def __init__(
        self,
        *,
        resource: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and reason:
                message = build_messages(
                    f"Payment required to access this {resource}: {reason}",
                    f"برای دسترسی به {resource}، پرداخت لازم است: {reason}",
                )
            elif resource:
                message = build_messages(
                    f"Payment required to access this {resource}",
                    f"برای دسترسی به {resource}، پرداخت لازم است.",
                )
            elif reason:
                message = build_messages(
                    f"Payment required: {reason}",
                    f"پرداخت لازم است: {reason}",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            reason=reason,
            **kwargs,
        )


class ResourceForbiddenError(ResourceError):
    """Raised when the caller lacks permission for the resource."""

    status_code = 403
    error_code = "forbidden"
    default_message = "You are not authorized to access this resource"
    default_message_fa = "شما اجازه دسترسی به این بخش را ندارید."

    def __init__(
        self,
        *,
        resource: str | None = None,
        action: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and action:
                message = build_messages(
                    f"You are not authorized to {action} this {resource}",
                    f"شما اجازه {action} این {resource} را ندارید.",
                )
            elif resource:
                message = build_messages(
                    f"You are not authorized to access this {resource}",
                    f"شما اجازه دسترسی به {resource} را ندارید.",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            action=action,
            **kwargs,
        )


class ResourceConflictError(ResourceError):
    """Raised when the resource state conflicts with the request."""

    status_code = 409
    error_code = "resource_conflict"
    default_message = "The resource is in a conflicting state"
    default_message_fa = (
        "به‌دلیل تداخل در وضعیت فعلی، این درخواست قابل انجام نیست."
    )

    def __init__(
        self,
        *,
        resource: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and reason:
                message = build_messages(
                    f"{resource} conflict: {reason}",
                    f"در {resource} تداخلی پیش آمده است: {reason}",
                )
            elif reason:
                message = build_messages(reason, reason)
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            reason=reason,
            **kwargs,
        )


class ResourceGoneError(ResourceError):
    """Raised when a resource existed but is permanently unavailable."""

    status_code = 410
    error_code = "resource_gone"
    default_message = "Resource is no longer available"
    default_message_fa = "این مورد دیگر در دسترس نیست."

    def __init__(
        self,
        *,
        resource: str | None = None,
        uid: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and uid:
                message = build_messages(
                    f"{resource} with id '{uid}' is no longer available",
                    f"{resource} با شناسه «{uid}» دیگر در دسترس نیست.",
                )
            elif resource:
                message = build_messages(
                    f"{resource} is no longer available",
                    f"{resource} دیگر در دسترس نیست.",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            uid=uid,
            **kwargs,
        )


class ResourceLockedError(ResourceError):
    """Raised when a resource is locked and cannot be modified."""

    status_code = 423
    error_code = "resource_locked"
    default_message = "Resource is locked"
    default_message_fa = "این مورد در حال حاضر قفل است و قابل تغییر نیست."

    def __init__(
        self,
        *,
        resource: str | None = None,
        uid: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize with optional context fields and message overrides."""
        if message is None:
            if resource and uid:
                message = build_messages(
                    f"{resource} with id '{uid}' is locked",
                    (
                        f"{resource} با شناسه «{uid}» قفل شده و "
                        "فعلاً قابل ویرایش نیست."
                    ),
                )
            elif resource:
                message = build_messages(
                    f"{resource} is locked",
                    f"{resource} قفل شده و فعلاً قابل ویرایش نیست.",
                )
        super().__init__(
            detail=detail,
            message=message,
            resource=resource,
            uid=uid,
            **kwargs,
        )
