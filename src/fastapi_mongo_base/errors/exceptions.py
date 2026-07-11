"""Exceptions for the fastapi-mongo-base package."""

from .base import BaseHTTPException
from .http import (
    AlreadyExistsError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PaymentRequiredError,
    ServerError,
    UnauthorizedError,
)

__all__ = [
    "AlreadyExistsError",
    "BadRequestError",
    "BaseHTTPException",
    "ConflictError",
    "ForbiddenError",
    "NotFoundError",
    "PaymentRequiredError",
    "ServerError",
    "UnauthorizedError",
]
