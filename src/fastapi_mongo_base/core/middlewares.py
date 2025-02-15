import logging
import time

import fastapi
from fastapi import Request
from fastapi.responses import PlainTextResponse
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


class DynamicCORSMiddleware(BaseHTTPMiddleware):

    async def get_allowed_origins(self, origin, **kwargs):
        from ufaas_fastapi_business.models import Business

        business = await Business.get_by_origin(origin)
        if not business:
            return []
        return business.config.allowed_origins

    async def dispatch(self, request: fastapi.Request, call_next):
        origin = request.headers.get("origin")
        allowed_origins = await self.get_allowed_origins(origin=request.url.hostname)
        headers = {}
        if origin in allowed_origins:
            headers = {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, *",
            }

        if request.method == "OPTIONS":
            return PlainTextResponse("", status_code=200, headers=headers)

        # if origin and origin not in allowed_origins:
        #     raise BaseHTTPException(
        #         status_code=403,
        #         error="origin_not_allowed",
        #         message="Origin not allowed",
        #     )

        response: fastapi.Response = await call_next(request)
        response.headers.update(headers)
        return response


class TimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        end_time = time.time()
        response.headers["X-Delivery-Time"] = str(end_time - start_time)

        return response
