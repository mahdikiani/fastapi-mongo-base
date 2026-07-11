"""HTTP request monitoring middleware for FastAPI applications."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable
from http import HTTPStatus
from typing import ClassVar

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

RequestEndpoint = Callable[[Request], Awaitable[Response]]


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Collect Prometheus HTTP metrics for a FastAPI/Starlette app.

    The middleware records request count, in-progress requests, and request
    latency. Metrics are labelled by HTTP method, route template, and status
    code so endpoint-level latency can be queried without exploding label
    cardinality from path parameters.

    Example:
        app.add_middleware(PrometheusMiddleware)

    """

    DEFAULT_EXCLUDED_PATHS: ClassVar[set[str]] = {
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    DEFAULT_BUCKETS: ClassVar[tuple[float, ...]] = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        0.75,
        1.0,
        2.5,
        5.0,
        7.5,
        10.0,
    )

    REQUESTS_TOTAL: ClassVar[Counter] = Counter(
        "http_requests_total",
        "Total number of HTTP requests.",
        ("method", "endpoint", "status_code"),
    )
    REQUESTS_IN_PROGRESS: ClassVar[Gauge] = Gauge(
        "http_requests_in_progress",
        "Number of HTTP requests currently being processed.",
        ("method", "endpoint"),
    )
    REQUEST_LATENCY_SECONDS: ClassVar[Histogram] = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds.",
        ("method", "endpoint", "status_code"),
        buckets=DEFAULT_BUCKETS,
    )

    def __init__(
        self,
        app: ASGIApp,
        *,
        excluded_paths: Iterable[str] | None = None,
    ) -> None:
        """
        Initialize the Prometheus metrics middleware.

        Args:
            app: ASGI application instance.
            excluded_paths: Exact URL paths that should not be measured.

        """
        super().__init__(app)
        self.excluded_paths = set(
            excluded_paths or self.DEFAULT_EXCLUDED_PATHS
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestEndpoint,
    ) -> Response:
        """
        Measure request metrics and forward the request downstream.

        Args:
            request: Incoming HTTP request.
            call_next: Next middleware or route handler.

        Returns:
            HTTP response returned by downstream application.

        Raises:
            Exception: Re-raises downstream exceptions after recording metrics.

        """
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        method = request.method
        endpoint = self._get_endpoint(request)
        status_code = str(HTTPStatus.INTERNAL_SERVER_ERROR.value)
        start_time = time.perf_counter()

        in_progress = self.REQUESTS_IN_PROGRESS.labels(
            method=method,
            endpoint=endpoint,
        )
        in_progress.inc()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = str(HTTPStatus.INTERNAL_SERVER_ERROR.value)
            raise
        else:
            return response
        finally:
            elapsed = time.perf_counter() - start_time
            in_progress.dec()
            self.REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).inc()
            self.REQUEST_LATENCY_SECONDS.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
            ).observe(elapsed)

    @staticmethod
    def _get_endpoint(request: Request) -> str:
        """
        Return the matched route path template for a request.

        Args:
            request: Incoming HTTP request.

        Returns:
            Route template when available, otherwise the raw URL path.

        """
        route = request.scope.get("route")
        path = getattr(route, "path", None)
        if isinstance(path, str):
            return path
        return request.url.path
