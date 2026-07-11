"""Tests for timezone helpers."""

from __future__ import annotations

from datetime import datetime

import pytz

from src.fastapi_mongo_base.utils import timezone


def test_iso_tz_formats_aware_datetime() -> None:
    """iso_tz returns ISO string without microseconds."""
    dt = datetime(2024, 6, 1, 12, 30, 45, tzinfo=pytz.UTC)
    assert timezone.iso_tz(dt, pytz.UTC) == "2024-06-01T12:30:45Z"


def test_iso_tz_localizes_naive_datetime() -> None:
    """iso_tz attaches timezone to naive datetimes."""
    dt = datetime(2024, 6, 1, 12, 0, 0)
    result = timezone.iso_tz(dt, pytz.UTC)
    assert result.startswith("2024-06-01T12:00:00")


def test_ensure_aware_and_unaware() -> None:
    """ensure_aware and ensure_unaware toggle tzinfo."""
    naive = datetime(2024, 1, 1, 8, 0, 0)
    aware = timezone.ensure_aware(naive, pytz.UTC)
    assert aware.tzinfo is not None
    back = timezone.ensure_unaware(aware)
    assert back.tzinfo is None
