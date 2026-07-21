"""Middleware for request-scoped trace ID propagation."""

from fastapi import Request, Response
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)

from ..utils.trace import (
    TRACE_ID_HEADER,
    request_trace_id,
    resolve_trace_id,
)


class TraceMiddleware(BaseHTTPMiddleware):
    """Bind ``X-Trace-ID`` to request context and echo it on responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Process request and bind trace ID to request state and context.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response from the downstream handler with ``X-Trace-ID`` set.

        """
        trace_id = resolve_trace_id(request.headers.get(TRACE_ID_HEADER))
        request.state.trace_id = trace_id
        token = request_trace_id.set(trace_id)
        try:
            response = await call_next(request)
            response.headers[TRACE_ID_HEADER] = trace_id
            return response
        finally:
            request_trace_id.reset(token)
