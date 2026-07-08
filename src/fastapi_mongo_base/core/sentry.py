"""Optional Sentry error tracking integration."""

from __future__ import annotations

import logging

from .config import Settings

logger = logging.getLogger(__name__)


def setup_sentry(settings: Settings) -> bool:
    """
    Initialize Sentry when a DSN is configured and sentry-sdk is installed.

    Sentry must be initialized before the FastAPI application is created so
    request handling and unhandled exceptions are instrumented correctly.

    Args:
        settings: Application settings instance.

    Returns:
        True when Sentry was initialized, False otherwise.

    """
    dsn = getattr(settings, "sentry_dsn", None)
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning(
            "Sentry DSN is configured but sentry-sdk is not installed. "
            "Install with: pip install 'fastapi-mongo-base[sentry]'"
        )
        return False

    init_kwargs: dict[str, object] = {
        "dsn": dsn,
        "integrations": [
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    }

    if settings.debug:
        init_kwargs["debug"] = True

    environment = getattr(settings, "sentry_environment", None)
    if environment:
        init_kwargs["environment"] = environment

    release = getattr(settings, "sentry_release", None)
    if release:
        init_kwargs["release"] = release

    traces_sample_rate = getattr(settings, "sentry_traces_sample_rate", None)
    if traces_sample_rate is not None:
        init_kwargs["traces_sample_rate"] = traces_sample_rate

    profiles_sample_rate = getattr(
        settings, "sentry_profiles_sample_rate", None
    )
    if profiles_sample_rate is not None:
        init_kwargs["profiles_sample_rate"] = profiles_sample_rate

    send_default_pii = getattr(settings, "sentry_send_default_pii", False)
    if send_default_pii:
        init_kwargs["send_default_pii"] = True

    sentry_sdk.init(**init_kwargs)
    logger.info(
        "Sentry initialized (environment=%s, release=%s)",
        environment or "default",
        release or "unset",
    )
    return True
