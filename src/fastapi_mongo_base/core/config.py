"""FastAPI server configuration."""

import dataclasses
import json
import logging.config
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from singleton import Singleton


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
    project_name: str = Field(default="PROJECT", validation_alias="PROJECT_NAME")
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
    mongo_uri: str = "mongodb://mongo:27017/"
    mongo_server_selection_timeout_ms: int = 5000
    mongo_connect_timeout_ms: int = 5000


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
        cls, console_level: str = "INFO", **kwargs: Any
    ) -> dict[str, object]:
        """
        Get logging configuration dictionary.

        Args:
            console_level: Logging level for console handler.
            **kwargs: Additional keyword arguments.

        Returns:
            Dictionary with logging configuration.
        """
        log_config = {
            "formatters": {
                "standard": {
                    "format": "[{levelname} : {filename}:{lineno} : {asctime} -> {funcName:10}] {message}",  # noqa: E501
                    "style": "{",
                }
            },
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
            "version": 1,
        }
        return log_config

    @classmethod
    def config_logger(cls) -> None:
        """Configure Python logging with settings from get_log_config."""
        log_config = cls.get_log_config()
        if log_config["handlers"].get("file"):
            (getattr(cls, "base_dir", Path(".")) / "logs").mkdir(
                parents=True, exist_ok=True
            )

        logging.config.dictConfig(cls.get_log_config())
