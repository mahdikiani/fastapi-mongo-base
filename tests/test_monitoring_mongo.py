"""Tests for MongoDB pool monitoring metrics."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("prometheus_client")

from src.fastapi_mongo_base.monitoring import mongo as mongo_metrics
from src.fastapi_mongo_base.monitoring.mongo import DatabasePoolMonitor


def _counter_value(counter: object, **labels: str) -> float:
    return counter.labels(**labels)._value.get()  # type: ignore[union-attr]


def _gauge_value(gauge: object, **labels: str) -> float:
    return gauge.labels(**labels)._value.get()  # type: ignore[union-attr]


@pytest.fixture()
def monitor() -> DatabasePoolMonitor:
    """Return a pool monitor with a unique database label per test."""
    return DatabasePoolMonitor(database_name="monitoring-test-db")


def test_implements_all_connection_pool_listener_methods(
    monitor: DatabasePoolMonitor,
) -> None:
    """Every ConnectionPoolListener hook must be implemented."""
    from pymongo import monitoring

    listener_methods = [
        name
        for name in dir(monitoring.ConnectionPoolListener)
        if name.startswith("connection_") or name.startswith("pool_")
    ]

    event = SimpleNamespace(
        address=("localhost", 27017),
        connection_id=1,
        reason="timeout",
    )

    for method_name in listener_methods:
        method = getattr(monitor, method_name)
        method(event)


def test_connection_lifecycle_updates_gauges_and_counters(
    monitor: DatabasePoolMonitor,
) -> None:
    """
    A cycle updates pool gauges and counters.

    A ready/checkout/checkin/close cycle updates pool gauges and counters.
    """
    database = monitor.database_name
    event = SimpleNamespace(
        address=("localhost", 27017),
        connection_id=1,
        reason="stale",
    )

    created_before = _counter_value(
        mongo_metrics.connections_created_total,
        database=database,
    )
    ready_before = _counter_value(
        mongo_metrics.connections_ready_total,
        database=database,
    )

    monitor.connection_created(event)
    monitor.connection_ready(event)

    assert (
        _counter_value(
            mongo_metrics.connections_created_total,
            database=database,
        )
        == created_before + 1
    )
    assert (
        _counter_value(
            mongo_metrics.connections_ready_total,
            database=database,
        )
        == ready_before + 1
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="available",
        )
        == 1
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="in_use",
        )
        == 0
    )

    started_before = _counter_value(
        mongo_metrics.checkouts_started_total,
        database=database,
    )
    monitor.connection_check_out_started(event)
    monitor.connection_checked_out(event)

    assert (
        _counter_value(
            mongo_metrics.checkouts_started_total,
            database=database,
        )
        == started_before + 1
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="available",
        )
        == 0
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="in_use",
        )
        == 1
    )

    monitor.connection_checked_in(event)

    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="available",
        )
        == 1
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="in_use",
        )
        == 0
    )

    closed_before = _counter_value(
        mongo_metrics.connections_closed_total,
        database=database,
    )
    monitor.connection_closed(event)

    assert (
        _counter_value(
            mongo_metrics.connections_closed_total,
            database=database,
        )
        == closed_before + 1
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="available",
        )
        == 0
    )


def test_connection_check_out_failed_increments_counter_with_reason(
    monitor: DatabasePoolMonitor,
) -> None:
    """Failed checkouts must be counted with their failure reason."""
    database = monitor.database_name
    event = MagicMock()
    event.reason = "timeout"

    before = _counter_value(
        mongo_metrics.checkouts_failed_total,
        database=database,
        reason="timeout",
    )

    monitor.connection_check_out_failed(event)

    assert (
        _counter_value(
            mongo_metrics.checkouts_failed_total,
            database=database,
            reason="timeout",
        )
        == before + 1
    )


def test_pool_cleared_resets_connection_gauges(
    monitor: DatabasePoolMonitor,
) -> None:
    """Clearing a pool resets available and in-use connection gauges."""
    database = monitor.database_name
    event = SimpleNamespace(address=("localhost", 27017))

    monitor.available_connections = 3
    monitor.in_use_connections = 2
    monitor._update_metrics()

    monitor.pool_cleared(event)

    assert monitor.available_connections == 0
    assert monitor.in_use_connections == 0
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="available",
        )
        == 0
    )
    assert (
        _gauge_value(
            mongo_metrics.pool_connections,
            database=database,
            state="in_use",
        )
        == 0
    )
