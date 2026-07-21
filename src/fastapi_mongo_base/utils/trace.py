"""Request-scoped trace ID helpers for cross-service correlation."""

from __future__ import annotations

from contextvars import ContextVar

import httpx
import uuid6

TRACE_ID_HEADER = "X-Trace-ID"

request_trace_id: ContextVar[str | None] = ContextVar(
    "request_trace_id",
    default=None,
)


def generate_trace_id() -> str:
    """Return a new UUID7 string suitable for use as a trace ID."""
    return str(uuid6.uuid7())


def get_trace_id() -> str | None:
    """Return the active request trace ID, if any."""
    return request_trace_id.get()


def get_trace_headers() -> dict[str, str]:
    """
    Build headers for propagating the active trace ID to downstream services.

    Returns an empty dict when no trace ID is bound (e.g. outside a request).

    Prefer ``create_async_client`` / ``TracedAsyncClient`` / ``install_trace``
    so outbound ``httpx`` calls pick up the header automatically. Manual merge
    remains available when needed::

        headers = {**get_trace_headers(), "Authorization": token}

    """
    trace_id = get_trace_id()
    if not trace_id:
        return {}
    return {TRACE_ID_HEADER: trace_id}


def resolve_trace_id(raw: str | None) -> str:
    """
    Normalize an inbound trace ID, generating one when missing or blank.

    Args:
        raw: Value from the inbound ``X-Trace-ID`` header, if present.

    Returns:
        A non-empty trace ID string.

    """
    if raw is None:
        return generate_trace_id()
    cleaned = raw.strip()
    if not cleaned:
        return generate_trace_id()
    return cleaned


def inject_trace_header(request: httpx.Request) -> None:
    """
    Inject ``X-Trace-ID`` into an httpx request when a trace is active.

    Sync hook for ``httpx.Client``. Does not overwrite an explicit header.
    """
    trace_id = get_trace_id()
    if not trace_id:
        return
    if TRACE_ID_HEADER in request.headers:
        return
    request.headers[TRACE_ID_HEADER] = trace_id


async def ainject_trace_header(  # ruff:ignore[unused-async]
    request: httpx.Request,
) -> None:
    """Async variant of :func:`inject_trace_header` for ``AsyncClient``."""
    inject_trace_header(request)


def merge_trace_event_hooks(
    event_hooks: dict[str, list[object]] | None = None,
    *,
    is_async: bool = False,
) -> dict[str, list[object]]:
    """
    Return ``event_hooks`` with a trace inject hook on the request list.

    Use ``is_async=True`` for ``AsyncClient`` (hooks are awaited). Safe to
    call multiple times; the matching hook is added at most once.
    """
    hook: object = (
        ainject_trace_header if is_async else inject_trace_header
    )
    hooks: dict[str, list[object]] = {
        key: list(value) for key, value in (event_hooks or {}).items()
    }
    request_hooks = list(hooks.get("request") or [])
    if hook not in request_hooks:
        request_hooks.insert(0, hook)
    hooks["request"] = request_hooks
    return hooks


def install_trace(
    client: httpx.Client | httpx.AsyncClient,
) -> httpx.Client | httpx.AsyncClient:
    """
    Attach trace injection to an existing httpx client (in place).

    Returns the same client for chaining::

        client = install_trace(httpx.AsyncClient(base_url=...))

    """
    is_async = isinstance(client, httpx.AsyncClient)
    hook: object = (
        ainject_trace_header if is_async else inject_trace_header
    )
    request_hooks = client.event_hooks.setdefault("request", [])
    if hook not in request_hooks:
        request_hooks.insert(0, hook)
    return client


def create_client(**kwargs: object) -> httpx.Client:
    """Create a sync httpx ``Client`` that propagates ``X-Trace-ID``."""
    hooks = kwargs.get("event_hooks")
    kwargs["event_hooks"] = merge_trace_event_hooks(
        hooks if isinstance(hooks, dict) else None,
    )
    return httpx.Client(**kwargs)


def create_async_client(**kwargs: object) -> httpx.AsyncClient:
    """Create an ``AsyncClient`` that propagates ``X-Trace-ID``."""
    hooks = kwargs.get("event_hooks")
    kwargs["event_hooks"] = merge_trace_event_hooks(
        hooks if isinstance(hooks, dict) else None,
        is_async=True,
    )
    return httpx.AsyncClient(**kwargs)


class TracedAsyncClient(httpx.AsyncClient):
    """``AsyncClient`` subclass that always propagates ``X-Trace-ID``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialize with trace injection wired into event hooks."""
        hooks = kwargs.get("event_hooks")
        kwargs["event_hooks"] = merge_trace_event_hooks(
            hooks if isinstance(hooks, dict) else None,
            is_async=True,
        )
        super().__init__(*args, **kwargs)
