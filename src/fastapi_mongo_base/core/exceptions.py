from fastapi.exceptions import HTTPException

error_messages = {}


class BaseHTTPException(HTTPException):
    def __init__(self, status_code: int, error: str, message: str = None, detail: str = None, **kwargs):
        self.status_code = status_code
        self.error = error
        self.message = message
        if message is None:
            self.message = error_messages.get(error, error)
        if detail is None:
            detail = self.message
        self.detail = detail
        super().__init__(status_code, detail=detail, **kwargs)
