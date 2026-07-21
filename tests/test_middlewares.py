"""Basic tests for middleware shims and TimerMiddleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.fastapi_mongo_base.middlewares import TimerMiddleware


def test_middlewares_package_exports_timer() -> None:
    """Public middleware package should export TimerMiddleware."""
    from src.fastapi_mongo_base import middlewares

    assert middlewares.__all__ == [
        "TimerMiddleware",
        "TimezoneMiddleware",
        "TraceMiddleware",
    ]
    assert middlewares.TimerMiddleware is TimerMiddleware


def test_prometheus_middleware_reexports_monitoring_class() -> None:
    """Prometheus shim should point to monitoring middleware implementation."""
    pytest.importorskip("prometheus_client")

    from src.fastapi_mongo_base.middlewares.prometheus import (
        PrometheusMiddleware,
    )
    from src.fastapi_mongo_base.monitoring.middleware import (
        PrometheusMiddleware as MonitoringPrometheusMiddleware,
    )

    assert PrometheusMiddleware is MonitoringPrometheusMiddleware


def test_timer_middleware_adds_delivery_time_header() -> None:
    """TimerMiddleware should expose request duration in X-Delivery-Time."""
    app = FastAPI()
    app.add_middleware(TimerMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.status_code == 200
    assert "x-delivery-time" in response.headers
    assert float(response.headers["x-delivery-time"]) >= 0
