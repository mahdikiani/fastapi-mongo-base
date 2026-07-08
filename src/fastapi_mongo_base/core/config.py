"""FastAPI server configuration."""

import dataclasses
import json
import logging
import logging.config
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from singleton import Singleton


class JsonFormatter(logging.Formatter):
    """
    Logging formatter that outputs a single-line structured JSON object.

    Using json_advanced.dumps ensures special types (datetime, UUID,
    ObjectId, Pydantic models, etc.) are serialised without raising errors.
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


class ProjectSettings(BaseSettings):
    """Environment-backed settings loaded by pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    root_url: str = Field(
        default="http://localhost:8000",
        validation_alias="DOMAIN",
    )
    project_name: str = Field(
        default="PROJECT", validation_alias="PROJECT_NAME"
    )
    base_path: str = "/api/v1"
    worker_update_time: int = 180
    debug: bool = False

    @field_validator("worker_update_time")
    @classmethod
    def normalize_worker_update_time(cls, value: int) -> int:
        """
        Preserve the previous fallback for falsy worker update values.

        Args:
            value: Configured worker update interval.

        Returns:
            Worker update interval with the legacy fallback applied.

        """
        return value or 180

    cors_origins: str | None = Field(
        default=None,
        validation_alias="CORS_ORIGINS",
    )
    page_max_limit: int = 100
    mongo_uri: str = Field(
        default="mongodb://localhost:27017/", validation_alias="MONGO_URI"
    )
    mongo_server_selection_timeout_ms: int = 5000
    mongo_connect_timeout_ms: int = 5000
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    sentry_environment: str | None = Field(
        default=None,
        validation_alias="SENTRY_ENVIRONMENT",
    )
    sentry_release: str | None = Field(
        default=None,
        validation_alias="SENTRY_RELEASE",
    )
    sentry_traces_sample_rate: float | None = Field(
        default=None,
        validation_alias="SENTRY_TRACES_SAMPLE_RATE",
    )
    sentry_profiles_sample_rate: float | None = Field(
        default=None,
        validation_alias="SENTRY_PROFILES_SAMPLE_RATE",
    )
    sentry_send_default_pii: bool = Field(
        default=False,
        validation_alias="SENTRY_SEND_DEFAULT_PII",
    )
    log_format: Literal["json", "text"] = Field(
        default="json",
        validation_alias="LOG_FORMAT",
    )

    @classmethod
    def get_coverage_dir(cls) -> str:
        """
        Get the directory path for coverage reports.

        Returns:
            Path string to coverage directory.

        """
        return getattr(cls, "base_dir", Path(".")) / "htmlcov"

    @classmethod
    def get_log_config(
        cls,
        console_level: str = "INFO",
        log_format: str | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        """
        Get logging configuration dictionary.

        Args:
            console_level: Logging level for console handler.
            log_format: ``"json"`` for structured JSON output (default, suited
                for Kubernetes / log-aggregation pipelines) or ``"text"`` for
                the human-readable bracketed format.  When *None* the value is
                read from the ``log_format`` attribute on the class (which is
                itself populated from the ``LOG_FORMAT`` environment variable).
            **kwargs: Additional keyword arguments (reserved for subclasses).

        Returns:
            Dictionary with logging configuration.
        """
        resolved_format = log_format or getattr(cls, "log_format", "json")

        if resolved_format == "json":
            formatter_config: dict[str, object] = {"()": JsonFormatter}
        else:
            formatter_config = {
                "format": "[{levelname} : {filename}:{lineno} : {asctime} -> {funcName:10}] {message}",  # noqa: E501
                "style": "{",
            }

        return {
            "version": 1,
            "formatters": {"standard": formatter_config},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": console_level,
                    "formatter": "standard",
                }
            },
            "loggers": {
                "": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": True,
                },
            },
        }

    @classmethod
    def config_logger(cls) -> None:
        """Configure Python logging with settings from get_log_config."""
        log_format = project_settings.log_format
        log_config = cls.get_log_config(log_format=log_format)
        if log_config["handlers"].get("file"):
            (cls.get_coverage_dir() / "logs").mkdir(
                parents=True, exist_ok=True
            )
        logging.config.dictConfig(log_config)


project_settings = ProjectSettings()


@dataclasses.dataclass
class Settings(metaclass=Singleton):
    """Server config settings."""

    # base_dir: Path = Path(__file__).resolve().parent.parent  # noqa: ERA001
    root_url: str = project_settings.root_url
    project_name: str = project_settings.project_name
    base_path: str = project_settings.base_path
    worker_update_time: int = project_settings.worker_update_time
    debug: bool = project_settings.debug

    _cors_origins_str: str | None = project_settings.cors_origins

    @property
    def cors_origins(self) -> list[str]:
        """
        CORS allowed origins as a list.

        Returns:
            List of allowed origin URLs.

        """
        if self._cors_origins_str and "[" in self._cors_origins_str:
            return json.loads(self._cors_origins_str)
        if self._cors_origins_str:
            return [s.strip() for s in self._cors_origins_str.split(",")]
        return ["http://localhost:8000"]

    page_max_limit: int = project_settings.page_max_limit
    mongo_uri: str = project_settings.mongo_uri
    mongo_server_selection_timeout_ms: int = (
        project_settings.mongo_server_selection_timeout_ms
    )
    mongo_connect_timeout_ms: int = project_settings.mongo_connect_timeout_ms
    sentry_dsn: str | None = project_settings.sentry_dsn
    sentry_environment: str | None = project_settings.sentry_environment
    sentry_release: str | None = project_settings.sentry_release
    sentry_traces_sample_rate: float | None = (
        project_settings.sentry_traces_sample_rate
    )
    sentry_profiles_sample_rate: float | None = (
        project_settings.sentry_profiles_sample_rate
    )
    sentry_send_default_pii: bool = project_settings.sentry_send_default_pii
    log_format: str = project_settings.log_format

    @classmethod
    def get_coverage_dir(cls) -> str:
        """
        Get the directory path for coverage reports.

        Returns:
            Path string to coverage directory.

        """
        return project_settings.get_coverage_dir()

    @classmethod
    def get_log_config(
        cls,
        console_level: str = "INFO",
        log_format: str | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        """
        Get logging configuration dictionary.

        Args:
            console_level: Logging level for console handler.
            log_format: ``"json"`` for structured JSON output (default, suited
                for Kubernetes / log-aggregation pipelines) or ``"text"`` for
                the human-readable bracketed format.  When *None* the value is
                read from the ``log_format`` attribute on the class (which is
                itself populated from the ``LOG_FORMAT`` environment variable).
            **kwargs: Additional keyword arguments (reserved for subclasses).

        Returns:
            Dictionary with logging configuration.
        """
        return project_settings.get_log_config(
            console_level=console_level,
            log_format=log_format,
            **kwargs,
        )

    @classmethod
    def config_logger(cls) -> None:
        """Configure Python logging with settings from get_log_config."""
        log_format = getattr(cls, "log_format", "json")
        log_config = cls.get_log_config(log_format=log_format)
        if log_config["handlers"].get("file"):
            (getattr(cls, "base_dir", Path(".")) / "logs").mkdir(
                parents=True, exist_ok=True
            )
        logging.config.dictConfig(log_config)
