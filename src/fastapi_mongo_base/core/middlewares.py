import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class TimerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        end_time = time.time()
        response.headers["X-Delivery-Time"] = str(end_time - start_time)

        return response
