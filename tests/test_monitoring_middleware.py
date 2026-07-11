"""Tests for monitoring package exports and Prometheus middleware."""

from __future__ import annotations

import importlib.util
from unittest.mock import AsyncMock, MagicMock

import pytest

if importlib.util.find_spec("prometheus_client") is None:
    pytest.skip(
        "prometheus_client is required for monitoring tests",
        allow_module_level=True,
    )

from starlette.requests import Request
from starlette.responses import Response

from src.fastapi_mongo_base.monitoring.middleware import PrometheusMiddleware

SCOPE_TEMPLATE: dict[str, object] = {
    "type": "http",
    "scheme": "http",
    "server": ("testserver", 80),
    "headers": [],
    "query_string": b"",
}

DEFAULT_EXCLUDED = PrometheusMiddleware.DEFAULT_EXCLUDED_PATHS


# ---------------------------------------------------------------------------
# __init__ module -- lazy attribute access
# ---------------------------------------------------------------------------


class TestInit:
    """Tests for ``monitoring.__init__.__getattr__``."""

    def test_getattr_prometheus_middleware(self) -> None:
        """``__getattr__`` returns the ``PrometheusMiddleware`` class."""
        from src.fastapi_mongo_base import monitoring

        assert monitoring.PrometheusMiddleware is PrometheusMiddleware

    def test_getattr_database_pool_monitor(self) -> None:
        """``__getattr__`` returns the ``DatabasePoolMonitor`` class."""
        from src.fastapi_mongo_base import monitoring
        from src.fastapi_mongo_base.monitoring.mongo import DatabasePoolMonitor

        assert monitoring.DatabasePoolMonitor is DatabasePoolMonitor

    def test_getattr_setup_sentry(self) -> None:
        """``__getattr__`` returns the ``setup_sentry`` function."""
        from src.fastapi_mongo_base import monitoring
        from src.fastapi_mongo_base.monitoring.sentry import setup_sentry

        assert monitoring.setup_sentry is setup_sentry

    def test_getattr_unknown_raises(self) -> None:
        """``__getattr__`` raises ``AttributeError`` for unknown names."""
        from src.fastapi_mongo_base import monitoring

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = monitoring.NonExistentName

    def test_all_exports(self) -> None:
        """``__all__`` lists all public names."""
        from src.fastapi_mongo_base import monitoring

        assert monitoring.__all__ == [
            "DatabasePoolMonitor",
            "PrometheusMiddleware",
            "setup_sentry",
        ]


# ---------------------------------------------------------------------------
# Shared fixtures for middleware tests
# ---------------------------------------------------------------------------


def _make_scope(
    method: str = "GET",
    path: str = "/",
    route: object | None = None,
) -> dict[str, object]:
    """Build a minimal ASGI scope dict suitable for a Starlette ``Request``."""
    scope = dict(SCOPE_TEMPLATE)
    scope["method"] = method
    scope["path"] = path
    if route is not None:
        scope["route"] = route
    return scope


@pytest.fixture()
def mock_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Swap real prometheus metrics with fresh mocks for test isolation."""
    mock_total = MagicMock(spec=["labels"])
    mock_in_progress = MagicMock(spec=["labels"])
    mock_latency = MagicMock(spec=["labels"])

    monkeypatch.setattr(PrometheusMiddleware, "REQUESTS_TOTAL", mock_total)
    monkeypatch.setattr(
        PrometheusMiddleware,
        "REQUESTS_IN_PROGRESS",
        mock_in_progress,
    )
    monkeypatch.setattr(
        PrometheusMiddleware,
        "REQUEST_LATENCY_SECONDS",
        mock_latency,
    )

    return mock_total, mock_in_progress, mock_latency


# ---------------------------------------------------------------------------
# PrometheusMiddleware unit tests
# ---------------------------------------------------------------------------


class TestPrometheusMiddleware:
    """Tests for ``PrometheusMiddleware`` construction and helpers."""

    def test_init_default_excluded_paths(self) -> None:
        """Default ``excluded_paths`` matches ``DEFAULT_EXCLUDED_PATHS``."""
        app = MagicMock()
        middleware = PrometheusMiddleware(app)

        assert middleware.excluded_paths == DEFAULT_EXCLUDED

    def test_init_custom_excluded_paths(self) -> None:
        """Custom ``excluded_paths`` overrides the defaults."""
        app = MagicMock()
        custom = {"/custom", "/health"}
        middleware = PrometheusMiddleware(app, excluded_paths=custom)

        assert middleware.excluded_paths == custom

    def test_init_empty_excluded_paths_falls_back_to_default(self) -> None:
        """An empty set is falsy so ``__init__`` falls back to defaults."""
        app = MagicMock()
        middleware = PrometheusMiddleware(app, excluded_paths=set())

        assert middleware.excluded_paths == DEFAULT_EXCLUDED

    # _get_endpoint ---------------------------------------------------------

    def test_get_endpoint_with_route_path(self) -> None:
        """Returns the route template path when a route is matched."""
        route = MagicMock(path="/users/{user_id}")
        scope = _make_scope(method="GET", path="/users/42", route=route)
        request = Request(scope)

        result = PrometheusMiddleware._get_endpoint(request)

        assert result == "/users/{user_id}"

    def test_get_endpoint_fallback_url_path(self) -> None:
        """Returns the raw URL path when no route is matched."""
        scope = _make_scope(path="/some/unknown/path")
        request = Request(scope)

        result = PrometheusMiddleware._get_endpoint(request)

        assert result == "/some/unknown/path"

    def test_get_endpoint_route_missing_path(self) -> None:
        """Falls back to URL path when the route object has no path attr."""
        route = MagicMock(spec=[])  # no ``path`` attribute
        scope = _make_scope(path="/fallback", route=route)
        request = Request(scope)

        result = PrometheusMiddleware._get_endpoint(request)

        assert result == "/fallback"


# ---------------------------------------------------------------------------
# Dispatch behaviour
# ---------------------------------------------------------------------------


class TestDispatch:
    """Tests for ``PrometheusMiddleware.dispatch``."""

    @pytest.mark.asyncio
    async def test_excluded_path_skips_metrics(
        self,
        mock_metrics: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        """Requests to an excluded path bypass all metric recording."""
        mock_total, mock_in_progress, mock_latency = mock_metrics

        middleware = PrometheusMiddleware(
            MagicMock(),
            excluded_paths={"/excluded"},
        )

        scope = _make_scope(path="/excluded")
        request = Request(scope)
        call_next = AsyncMock(return_value=Response("ok", status_code=200))

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200
        call_next.assert_awaited_once_with(request)
        mock_in_progress.labels.assert_not_called()
        mock_total.labels.assert_not_called()
        mock_latency.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_request_records_metrics(
        self,
        mock_metrics: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        """Normal requests record in-progress, total, and latency metrics."""
        mock_total, mock_in_progress, mock_latency = mock_metrics

        middleware = PrometheusMiddleware(MagicMock())
        route = MagicMock(path="/items/{item_id}")
        scope = _make_scope(method="GET", path="/items/42", route=route)
        request = Request(scope)
        call_next = AsyncMock(
            return_value=Response(
                '{"ok": true}',
                status_code=200,
                media_type="application/json",
            ),
        )

        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200

        in_progress_labels = mock_in_progress.labels
        in_progress_labels.assert_called_once_with(
            method="GET",
            endpoint="/items/{item_id}",
        )
        in_progress_mock = in_progress_labels.return_value
        in_progress_mock.inc.assert_called_once()
        in_progress_mock.dec.assert_called_once()

        mock_total.labels.assert_called_once_with(
            method="GET",
            endpoint="/items/{item_id}",
            status_code="200",
        )
        mock_total.labels.return_value.inc.assert_called_once()

        mock_latency.labels.assert_called_once_with(
            method="GET",
            endpoint="/items/{item_id}",
            status_code="200",
        )
        mock_latency.labels.return_value.observe.assert_called_once()
        args, _kwargs = mock_latency.labels.return_value.observe.call_args
        (elapsed,) = args
        assert elapsed >= 0

    @pytest.mark.asyncio
    async def test_exception_records_metrics_and_re_raises(
        self,
        mock_metrics: tuple[MagicMock, MagicMock, MagicMock],
    ) -> None:
        """Exceptions record ``500`` metrics and are re-raised."""
        mock_total, mock_in_progress, mock_latency = mock_metrics

        middleware = PrometheusMiddleware(MagicMock())
        scope = _make_scope(method="POST", path="/fail")
        request = Request(scope)
        call_next = AsyncMock(side_effect=ValueError("something broke"))

        with pytest.raises(ValueError, match="something broke"):
            await middleware.dispatch(request, call_next)

        in_progress_labels = mock_in_progress.labels
        in_progress_labels.assert_called_once_with(
            method="POST",
            endpoint="/fail",
        )
        in_progress_mock = in_progress_labels.return_value
        in_progress_mock.inc.assert_called_once()
        in_progress_mock.dec.assert_called_once()

        mock_total.labels.assert_called_once_with(
            method="POST",
            endpoint="/fail",
            status_code="500",
        )
        mock_total.labels.return_value.inc.assert_called_once()

        mock_latency.labels.assert_called_once_with(
            method="POST",
            endpoint="/fail",
            status_code="500",
        )
        mock_latency.labels.return_value.observe.assert_called_once()
        args, _kwargs = mock_latency.labels.return_value.observe.call_args
        (elapsed,) = args
        assert elapsed >= 0
