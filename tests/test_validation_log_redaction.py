"""Validation error logs must not leak credentials."""

from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError

from fastapi_mongo_base.errors import handlers

CREDENTIAL = "uak-credential-value-1234567890"


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": headers,
        "query_string": b"",
        "client": ("test", 50000),
        "server": ("test", 80),
        "scheme": "http",
        "http_version": "1.1",
    })
    request.state.raw_body = b"{}"
    return request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    [
        b"authorization",
        b"x-api-key",
        b"api-key",
        b"cookie",
        b"proxy-authorization",
        b"x-auth-token",
        b"x-access-token",
        b"x-session-secret",
    ],
)
async def test_validation_log_redacts_credential_headers(
    header: bytes,
) -> None:
    """Credential headers are redacted; other headers stay readable."""
    request = _request([
        (header, CREDENTIAL.encode()),
        (b"user-agent", b"probe/1.0"),
    ])
    exc = RequestValidationError([
        {"loc": ("body", "file"), "msg": "Field required", "type": "missing"}
    ])

    with patch.object(handlers, "logger") as logger:
        response = await handlers.request_validation_exception_handler(
            request, exc
        )

    assert response.status_code == 422
    message, *args = logger.error.call_args.args
    logged = message % tuple(args)
    assert CREDENTIAL not in logged
    assert "[REDACTED]" in logged
    assert "probe/1.0" in logged
