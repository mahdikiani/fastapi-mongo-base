import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


# Create logging middleware
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log the request details
        # logging.info(f"Request: {request.method} {request.url}")
        # logging.info(f"Headers: {request.headers}")

        # You can also log other request details like body, client IP, etc.
        # Accessing the request body requires it to be async, managing it carefully since it is a stream

        response = await call_next(request)

        # You can also log response details here if needed
        logging.info(f"request: {request.method} {request.url} {response.status_code}")

        return response
