"""Backward compatibility aliases for HTTP client errors."""

from .http import (
    AlreadyExistsError,
    ConflictError,
    ForbiddenError,
    GoneError,
    LockedError,
    NotFoundError,
    PaymentRequiredError,
    ServerError,
)

ResourceNotFoundError = NotFoundError
ResourceAlreadyExistsError = AlreadyExistsError
ResourceConflictError = ConflictError
ResourcePaymentRequiredError = PaymentRequiredError
ResourceForbiddenError = ForbiddenError
ResourceGoneError = GoneError
ResourceLockedError = LockedError

__all__ = [
    "ResourceAlreadyExistsError",
    "ResourceConflictError",
    "ResourceForbiddenError",
    "ResourceGoneError",
    "ResourceLockedError",
    "ResourceNotFoundError",
    "ResourcePaymentRequiredError",
    "ServerError",
]
