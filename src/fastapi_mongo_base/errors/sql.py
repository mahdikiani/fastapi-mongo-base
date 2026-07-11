"""SQL connection errors."""


class SQLConnectionError(Exception):
    """Raised when SQL connection or initialization fails at startup."""

    def __init__(
        self,
        message: str = "Failed to connect to SQL database",
    ) -> None:
        """Initialize SQLConnectionError with a message."""
        super().__init__(message)
        self.message = message
