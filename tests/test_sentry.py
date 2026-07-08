"""Tests for optional Sentry integration."""

import builtins
import dataclasses
import sys
from unittest.mock import patch

import pytest

from src.fastapi_mongo_base.core.sentry import setup_sentry


@dataclasses.dataclass
class _TestSentrySettings:
    debug: bool = False
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    sentry_release: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_profiles_sample_rate: float | None = None
    sentry_send_default_pii: bool = False


def test_setup_sentry_skips_without_dsn() -> None:
    """Sentry should not initialize when no DSN is configured."""
    settings = _TestSentrySettings()
    assert setup_sentry(settings) is False


def test_setup_sentry_warns_when_sdk_missing() -> None:
    """Sentry should warn and skip when sentry-sdk is not installed."""
    settings = _TestSentrySettings(sentry_dsn="https://example@sentry.io/1")
    real_import = builtins.__import__
    sentry_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == "sentry_sdk" or key.startswith("sentry_sdk.")
    }

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    for key in sentry_modules:
        del sys.modules[key]

    try:
        with (
            patch(
                "src.fastapi_mongo_base.core.sentry.logger.warning"
            ) as warning_mock,
            patch("builtins.__import__", side_effect=mock_import),
        ):
            result = setup_sentry(settings)
    finally:
        sys.modules.update(sentry_modules)

    assert result is False
    warning_mock.assert_called_once()


def test_setup_sentry_initializes_with_dsn() -> None:
    """Sentry should initialize when DSN is set and sentry-sdk is available."""
    sentry_sdk = pytest.importorskip("sentry_sdk")
    with patch.object(sentry_sdk, "init") as init_mock:
        settings = _TestSentrySettings(
            sentry_dsn="https://example@sentry.io/1",
            sentry_environment="test",
            sentry_release="1.0.0",
            sentry_traces_sample_rate=0.5,
            sentry_profiles_sample_rate=0.1,
            sentry_send_default_pii=True,
        )

        assert setup_sentry(settings) is True
        init_mock.assert_called_once()
        kwargs = init_mock.call_args.kwargs
        assert kwargs["dsn"] == "https://example@sentry.io/1"
        assert kwargs["environment"] == "test"
        assert kwargs["release"] == "1.0.0"
        assert kwargs["traces_sample_rate"] == pytest.approx(0.5)
        assert kwargs["profiles_sample_rate"] == pytest.approx(0.1)
        assert kwargs["send_default_pii"] is True
        assert len(kwargs["integrations"]) == 2
        assert all(
            integration.transaction_style == "endpoint"
            for integration in kwargs["integrations"]
        )
