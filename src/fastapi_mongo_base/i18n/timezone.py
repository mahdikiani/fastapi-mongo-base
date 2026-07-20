"""Request timezone resolution and datetime serialization helpers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytz

from ..utils import timezone as tz_util
from .context import request_timezone

if TYPE_CHECKING:
    from fastapi import Request

TIMEZONE_HEADER = "x-timezone"


def parse_timezone(value: str | None) -> pytz.BaseTzInfo | None:
    """Parse an IANA timezone name, returning None when invalid."""
    if not value:
        return None
    try:
        return pytz.timezone(value.strip())
    except pytz.UnknownTimeZoneError:
        return None


def resolve_request_timezone(
    request: Request,
    *,
    user_timezone: str | pytz.BaseTzInfo | None = None,
) -> pytz.BaseTzInfo:
    """
    Resolve the active timezone for a request.

    Priority: user timezone > X-Timezone header > app TIMEZONE env.
    """
    for candidate in (
        user_timezone,
        request.headers.get(TIMEZONE_HEADER),
    ):
        if candidate is None:
            continue
        if isinstance(candidate, str):
            parsed = parse_timezone(candidate)
        else:
            parsed = candidate
        if parsed is not None:
            return parsed
    return tz_util.tz


def set_request_timezone(
    request: Request,
    timezone: pytz.BaseTzInfo,
) -> None:
    """Store the resolved timezone on the request and in context."""
    request.state.timezone = timezone
    request_timezone.set(timezone)


def apply_user_timezone(
    request: Request,
    user: object | None,
    *,
    attribute: str = "timezone",
) -> None:
    """Override request timezone when the authenticated user has one."""
    if user is None:
        return
    user_tz = getattr(user, attribute, None)
    if user_tz is None:
        return
    if isinstance(user_tz, str):
        parsed = parse_timezone(user_tz)
    elif isinstance(user_tz, pytz.BaseTzInfo):
        parsed = user_tz
    else:
        return
    if parsed is not None:
        set_request_timezone(request, parsed)


def serialize_response_datetime(dt: datetime) -> str:
    """Serialize a datetime for API responses in the request timezone."""
    target_tz = request_timezone.get() or tz_util.tz
    aware = tz_util.utc.localize(dt) if dt.tzinfo is None else dt
    return tz_util.iso_tz(aware, target_tz)


def localize_filter_datetime(
    dt: datetime,
    *,
    source_tz: pytz.BaseTzInfo | None = None,
) -> datetime:
    """Convert a naive or aware filter datetime to UTC for storage queries."""
    active_tz = source_tz or request_timezone.get() or tz_util.tz
    aware = active_tz.localize(dt) if dt.tzinfo is None else dt
    return aware.astimezone(tz_util.utc)
