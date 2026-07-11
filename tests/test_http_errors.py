"""Tests for HTTP API error exceptions."""

import pytest
from fastapi import HTTPException

from src.fastapi_mongo_base.errors.base import BaseHTTPException
from src.fastapi_mongo_base.errors.http import ServerError
from src.fastapi_mongo_base.errors.resource import (
    AlreadyExistsError,
    ConflictError,
    ForbiddenError,
    GoneError,
    LockedError,
    NotFoundError,
    PaymentRequiredError,
    ResourceAlreadyExistsError,
    ResourceConflictError,
    ResourceForbiddenError,
    ResourceGoneError,
    ResourceLockedError,
    ResourceNotFoundError,
    ResourcePaymentRequiredError,
)

HTTP_ERROR_CASES = [
    pytest.param(
        ServerError,
        500,
        "internal_server_error",
        "Internal server error",
        "خطای داخلی سرور رخ داده است",
        id="APIError",
    ),
    pytest.param(
        NotFoundError,
        404,
        "resource_not_found",
        "Resource not found",
        "یافت نشد",
        id="NotFoundError",
    ),
    pytest.param(
        AlreadyExistsError,
        409,
        "resource_already_exists",
        "Resource already exists",
        "نمونه‌ی مشابه وجود دارد",
        id="AlreadyExistsError",
    ),
    pytest.param(
        ConflictError,
        409,
        "resource_conflict",
        "Resource conflict",
        "اطلاعات ارسال شده تداخل دارد",
        id="ConflictError",
    ),
    pytest.param(
        PaymentRequiredError,
        402,
        "resource_payment_required",
        "Resource payment required",
        "برای دسترسی، پرداخت لازم است",
        id="PaymentRequiredError",
    ),
    pytest.param(
        ForbiddenError,
        403,
        "permission_denied",
        "Permission denied",
        "دسترسی غیر مجاز",
        id="ForbiddenError",
    ),
    pytest.param(
        GoneError,
        410,
        "resource_gone",
        "Resource gone",
        "در دسترس نیست",
        id="GoneError",
    ),
    pytest.param(
        LockedError,
        423,
        "resource_locked",
        "Resource locked",
        "قفل شده است",
        id="LockedError",
    ),
]

ALL_HTTP_ERROR_CLASSES = [case.values[0] for case in HTTP_ERROR_CASES]

LEGACY_ALIASES = [
    (ServerError, ServerError),
    (ResourceNotFoundError, NotFoundError),
    (ResourceAlreadyExistsError, AlreadyExistsError),
    (ResourceConflictError, ConflictError),
    (ResourcePaymentRequiredError, PaymentRequiredError),
    (ResourceForbiddenError, ForbiddenError),
    (ResourceGoneError, GoneError),
    (ResourceLockedError, LockedError),
]


@pytest.mark.parametrize(
    ("exc_cls", "status_code", "error_code", "message_en", "message_fa"),
    HTTP_ERROR_CASES,
)
def test_api_error_class_messages(
    exc_cls: type[BaseHTTPException],
    status_code: int,
    error_code: str,
    message_en: str,
    message_fa: str,
) -> None:
    """Each API error defines expected en/fa messages."""
    assert exc_cls.status_code == status_code
    assert exc_cls.error_code == error_code
    assert exc_cls.message_en == message_en
    assert exc_cls.message_fa == message_fa


@pytest.mark.parametrize(
    ("exc_cls", "status_code", "error_code", "message_en", "message_fa"),
    HTTP_ERROR_CASES,
)
def test_api_error_detail_and_bilingual_message(
    exc_cls: type[BaseHTTPException],
    status_code: int,
    error_code: str,
    message_en: str,
    message_fa: str,
) -> None:
    """Default detail matches message_en; message dict contains en and fa."""
    exc = exc_cls()

    assert exc.status_code == status_code
    assert exc.error_code == error_code
    assert exc.detail == message_en
    assert exc.message["en"] == message_en
    assert exc.message["fa"] == message_fa
    assert exc.message == {"en": message_en, "fa": message_fa}


@pytest.mark.parametrize(
    "exc_cls", ALL_HTTP_ERROR_CLASSES[1:], ids=lambda c: c.__name__
)
def test_api_errors_inherit_from_api_error(
    exc_cls: type[BaseHTTPException],
) -> None:
    """Every specialized API error extends APIError."""
    assert issubclass(exc_cls, BaseHTTPException)


def test_api_error_inheritance() -> None:
    """API errors extend the shared HTTP exception hierarchy."""
    for exc_cls in ALL_HTTP_ERROR_CLASSES:
        assert issubclass(exc_cls, BaseHTTPException)
        assert issubclass(exc_cls, HTTPException)


@pytest.mark.parametrize(
    ("exc_cls", "message_en", "message_fa"),
    [
        (case.values[0], case.values[3], case.values[4])
        for case in HTTP_ERROR_CASES
    ],
    ids=[case.id for case in HTTP_ERROR_CASES],
)
def test_api_error_custom_detail_preserves_bilingual_message(
    exc_cls: type[BaseHTTPException],
    message_en: str,
    message_fa: str,
) -> None:
    """A custom detail overrides detail only; en/fa messages stay unchanged."""
    custom_detail = f"Custom detail for {exc_cls.__name__}"
    exc = exc_cls(detail=custom_detail)

    assert exc.detail == custom_detail
    assert exc.message["en"] == message_en
    assert exc.message["fa"] == message_fa


def test_api_error_extra_data() -> None:
    """Additional keyword arguments are stored on the exception instance."""
    exc = NotFoundError(resource_id="abc-123")

    assert exc.data == {"resource_id": "abc-123"}


@pytest.mark.parametrize(("legacy", "canonical"), LEGACY_ALIASES)
def test_legacy_resource_error_aliases(
    legacy: type[BaseHTTPException],
    canonical: type[BaseHTTPException],
) -> None:
    """Resource* names remain aliases of the canonical API errors."""
    assert legacy is canonical
