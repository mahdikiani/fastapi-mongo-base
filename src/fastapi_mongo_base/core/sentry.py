"""Backward compatibility shim. Prefer fastapi_mongo_base.monitoring.sentry."""

from ..monitoring.sentry import setup_sentry

__all__ = ["setup_sentry"]
