"""Middleware for request-scoped timezone resolution."""

from fastapi import Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)

from ..i18n.context import request_timezone
from ..i18n.timezone import resolve_request_timezone


class TimezoneMiddleware(BaseHTTPMiddleware):
    """Resolve request timezone from headers and expose it via context."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process request and bind timezone to request state and context.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response from the downstream handler.

        """
        timezone = resolve_request_timezone(request)
        request.state.timezone = timezone
        token = request_timezone.set(timezone)
        try:
            return await call_next(request)
        finally:
            request_timezone.reset(token)
