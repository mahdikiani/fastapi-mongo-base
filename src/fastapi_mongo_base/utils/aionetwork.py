import logging
from io import BytesIO
from typing import Literal

import aiofiles
import httpx


async def prepare_url(url: str) -> str:
    """Ensure the URL is valid and starts with http or https."""
    if url is None:
        raise ValueError("url is required")
    return url if url.startswith("http") else f"https://{url}"


async def log_error(url: str, status_code: int, text: str, **kwargs):
    """Log request errors."""
    data = kwargs.get("data")
    if not isinstance(data, str):
        data = str(data)

    logging.error(f"Error in aio_request {url} {data[:100]}: {status_code} {text}")


async def handle_binary_response(response: httpx.Response) -> BytesIO:
    """Handle binary response."""
    resp_bytes = BytesIO(await response.aread())
    resp_bytes.seek(0)
    return resp_bytes


async def aio_request_client(
    client: httpx.AsyncClient,
    *,
    method: str = "get",
    url: str = None,
    response_type: Literal["json", "binary", "text", "bytes"] = "json",
    **kwargs,
):
    """Perform an HTTP request and return the desired response type."""
    url = await prepare_url(url)

    raise_exception = kwargs.pop("raise_exception", True)

    response = await client.request(method, url, **kwargs)

    try:
        response.raise_for_status()
    except Exception as e:
        await log_error(url, response.status_code, response.text, **kwargs)
        if raise_exception:
            raise e

    if response_type == "binary":
        return await handle_binary_response(response)
    if response_type == "bytes":
        return response.content
    if response_type == "json":
        return response.json()
    return response.text


async def aio_request(*, method: str = "get", url: str = None, **kwargs) -> dict:
    async with httpx.AsyncClient() as client:
        return await aio_request_client(client, method=method, url=url, **kwargs)


async def aio_request_binary(
    *, method: str = "get", url: str = None, **kwargs
) -> BytesIO:
    return await aio_request(method=method, url=url, response_type="binary", **kwargs)


async def aio_download(
    url: str, filename: str, *, chunk_size: int = 8192, **kwargs
) -> str:
    """Download a file and save it locally."""
    url = await prepare_url(url)
    raise_exception = kwargs.pop("raise_exception", True)

    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, **kwargs) as response:
            if raise_exception:
                response.raise_for_status()

            async with aiofiles.open(filename, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=chunk_size):
                    await f.write(chunk)

    return filename
