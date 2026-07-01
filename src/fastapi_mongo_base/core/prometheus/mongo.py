"""Prometheus metrics for MongoDB connection pools."""

from __future__ import annotations

from threading import Lock

from prometheus_client import Counter, Gauge
from pymongo import monitoring

pool_connections = Gauge(
    "mongodb_pool_connections",
    "Current MongoDB pool connections",
    ["database", "state"],
)

connections_created_total = Counter(
    "mongodb_pool_connections_created_total",
    "Total MongoDB connections created",
    ["database"],
)

connections_closed_total = Counter(
    "mongodb_pool_connections_closed_total",
    "Total MongoDB connections closed",
    ["database"],
)


class DatabasePoolMonitor(monitoring.ConnectionPoolListener):
    """Monitor MongoDB connection pool events and update Prometheus metrics."""

    def __init__(self, database_name: str) -> None:
        """Initialize the monitor for a MongoDB database."""
        self.database_name = database_name
        self._lock = Lock()

        self.available_connections = 0
        self.in_use_connections = 0

    def _update_metrics(self) -> None:
        pool_connections.labels(
            database=self.database_name,
            state="available",
        ).set(self.available_connections)

        pool_connections.labels(
            database=self.database_name,
            state="in_use",
        ).set(self.in_use_connections)

    def pool_created(self, event: monitoring.PoolCreatedEvent) -> None:
        """Handle MongoDB pool creation events."""
        del event

    def pool_ready(self, event: monitoring.PoolReadyEvent) -> None:
        """Handle MongoDB pool readiness events."""
        del event

    def pool_cleared(self, event: monitoring.PoolClearedEvent) -> None:
        """Handle MongoDB pool clearing events."""
        del event

    def pool_closed(self, event: monitoring.PoolClosedEvent) -> None:
        """Handle MongoDB pool closure events."""
        del event

    def connection_created(
        self,
        event: monitoring.ConnectionCreatedEvent,
    ) -> None:
        """Record a MongoDB connection creation event."""
        del event

        with self._lock:
            self.available_connections += 1

            connections_created_total.labels(
                database=self.database_name,
            ).inc()

            self._update_metrics()

    def connection_closed(
        self,
        event: monitoring.ConnectionClosedEvent,
    ) -> None:
        """Record a MongoDB connection closure event."""
        del event

        with self._lock:
            self.available_connections = max(
                0,
                self.available_connections - 1,
            )

            connections_closed_total.labels(
                database=self.database_name,
            ).inc()

            self._update_metrics()

    def connection_checked_out(
        self,
        event: monitoring.ConnectionCheckedOutEvent,
    ) -> None:
        """Record a MongoDB connection checkout event."""
        del event

        with self._lock:
            self.available_connections = max(
                0,
                self.available_connections - 1,
            )
            self.in_use_connections += 1

            self._update_metrics()

    def connection_checked_in(
        self,
        event: monitoring.ConnectionCheckedInEvent,
    ) -> None:
        """Record a MongoDB connection checkin event."""
        del event

        with self._lock:
            self.in_use_connections = max(
                0,
                self.in_use_connections - 1,
            )
            self.available_connections += 1

            self._update_metrics()
