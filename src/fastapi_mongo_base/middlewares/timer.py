"""Middleware components for FastAPI."""

import time

from fastapi import Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)


class TimerMiddleware(BaseHTTPMiddleware):
    """Middleware to measure request processing time in response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process request and add X-Delivery-Time header.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response with X-Delivery-Time header added.

        """
        start_time = time.time()
        response = await call_next(request)
        end_time = time.time()
        response.headers["X-Delivery-Time"] = str(end_time - start_time)

        return response
