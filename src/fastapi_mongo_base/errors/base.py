"""Base HTTP exception for structured API error responses."""

from fastapi.exceptions import HTTPException

from ..i18n import localized


class BaseHTTPException(HTTPException):
    """
    Base HTTP exception with multi-language message support.

    Attributes:
        status_code: HTTP status code.
        error: Error code string.
        message: Dictionary of language-specific error messages.
        detail: Error detail string.
        data: Additional error data.

    """

    status_code: int = 500
    error_code: str = "unknown_error"
    message_en: str = "An unknown error occurred"
    message_fa: str | None = "یک خطای ناشناخته رخ داده است"

    def __init__(
        self,
        status_code: int | None = None,
        error_code: str | None = None,
        detail: str | None = None,
        message: dict | None = None,
        **kwargs: object,
    ) -> None:
        """
        Initialize base HTTP exception.

        Args:
            status_code: HTTP status code.
            error_code: Error code string.
            detail: Optional error detail message.
            message: Optional dictionary of language-specific messages.
            **kwargs: Additional error data.

        """
        self.status_code = status_code or self.status_code
        self.error_code = error_code or self.error_code
        if message is None:
            if self.message_en and self.message_fa:
                self.message = localized(self.message_en, self.message_fa)
            else:
                self.message = localized(detail or self.message_en)
        else:
            if isinstance(message, str):
                message = {"en": message}
            self.message = message
        self.detail = detail or str(self.message.get("en"))
        self.data = kwargs
        super().__init__(self.status_code, detail=self.detail)
