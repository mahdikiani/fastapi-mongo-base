"""Redis connection errors."""

from __future__ import annotations


class RedisConnectionError(Exception):
    """Raised when Redis connection or initialization fails at startup."""

    def __init__(self, message: str = "Failed to connect to Redis") -> None:
        """Initialize RedisConnectionError with a message."""
        super().__init__(message)
        self.message = message
