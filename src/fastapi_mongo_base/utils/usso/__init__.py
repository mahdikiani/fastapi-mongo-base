"""USSO integration helpers (optional ``[usso]`` extra)."""

from .principals import (
    SERVICE_SUB_TYPES,
    is_service_auth,
    is_service_request,
    is_service_user,
)

__all__ = [
    "SERVICE_SUB_TYPES",
    "is_service_auth",
    "is_service_request",
    "is_service_user",
]
