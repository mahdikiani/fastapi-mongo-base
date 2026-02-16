"""Timezone utilities for the application."""

import os
from datetime import datetime

import pytz

tz = pytz.timezone(os.getenv("TIMEZONE", "UTC"))
utc = pytz.timezone("UTC")


def iso_tz(dt: datetime, timezone: pytz.timezone = tz) -> str:
    """
    Convert a datetime object to a ISO string with the given timezone.

    Remove microseconds and replace +00:00 with Z.

    Args:
        dt: The datetime object to convert.
        timezone: The timezone to convert the datetime object to.

    Returns:
        The ISO string with the given timezone.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone)
    dt = dt.astimezone(timezone)

    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
