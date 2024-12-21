from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class OriginalHostMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        original_host = request.headers.get("X-Original-Host")

        if original_host:
            new_url = request.url.replace(netloc=original_host)
            request._url = new_url

            for i, el in enumerate(request.scope["headers"]):
                k, v = el
                key = k.decode("utf-8")

                if key.lower() in ["host", "x-forwarded-host"]:
                    request.scope["headers"][i] = (k, original_host.encode("utf-8"))

        # Proceed with the next middleware or request handler
        response = await call_next(request)
        return response
