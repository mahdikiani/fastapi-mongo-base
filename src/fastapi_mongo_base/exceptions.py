error_messages = {}


class BaseHTTPException(Exception):
    def __init__(self, status_code: int, error: str, message: str = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        if message is None:
            self.message = error_messages.get(error, error)
        super().__init__(message)
