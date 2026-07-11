"""Application monitoring: HTTP metrics, MongoDB pool, and Sentry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .middleware import PrometheusMiddleware
    from .mongo import DatabasePoolMonitor
    from .sentry import setup_sentry

__all__ = [
    "DatabasePoolMonitor",
    "PrometheusMiddleware",
    "setup_sentry",
]


def __getattr__(name: str) -> object:
    if name == "PrometheusMiddleware":
        from .middleware import PrometheusMiddleware

        return PrometheusMiddleware
    if name == "DatabasePoolMonitor":
        from .mongo import DatabasePoolMonitor

        return DatabasePoolMonitor
    if name == "setup_sentry":
        from .sentry import setup_sentry

        return setup_sentry
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
