"""Structured logging formatters."""

from __future__ import annotations

import logging

import json_advanced as json


class JsonFormatter(logging.Formatter):
    """
    Logging formatter that outputs a single-line structured JSON object.

    Uses ``json_advanced.dumps`` so special types (datetime, UUID, ObjectId,
    Pydantic models, etc.) serialize without raising errors.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serialise *record* to a JSON string."""
        data: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "filename": record.filename,
            "lineno": record.lineno,
            "funcName": record.funcName,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            data["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(data, ensure_ascii=False)
