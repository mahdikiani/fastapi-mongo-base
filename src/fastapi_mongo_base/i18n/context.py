"""Request-scoped context for internationalization helpers."""

from contextvars import ContextVar

import pytz

request_timezone: ContextVar[pytz.BaseTzInfo | None] = ContextVar(
    "request_timezone",
    default=None,
)
