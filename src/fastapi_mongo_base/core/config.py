"""FastAPI server configuration."""

import dataclasses
import json
import logging.config
import os
from pathlib import Path

import dotenv
from singleton import Singleton

dotenv.load_dotenv()


@dataclasses.dataclass
class Settings(metaclass=Singleton):
    """Server config settings."""

    # base_dir: Path = Path(__file__).resolve().parent.parent  # noqa: ERA001
    root_url: str = os.getenv("DOMAIN") or "http://localhost:8000"
    project_name: str = os.getenv("PROJECT_NAME") or "PROJECT"
    base_path: str = "/api/v1"
    worker_update_time: int = (
        int(os.getenv("WORKER_UPDATE_TIME", default=180)) or 180
    )
    debug: bool = os.getenv("DEBUG", default="false").lower() == "true"

    _cors_origins_str: str | None = os.getenv("CORS_ORIGINS")

    @property
    def cors_origins(self) -> list[str]:
        if self._cors_origins_str and "[" in self._cors_origins_str:
            return json.loads(self._cors_origins_str)
        elif self._cors_origins_str:
            return [s.strip() for s in self._cors_origins_str.split(",")]
        return ["http://localhost:8000"]

    page_max_limit: int = 100
    mongo_uri: str = os.getenv("MONGO_URI", default="mongodb://mongo:27017/")

    @classmethod
    def get_coverage_dir(cls) -> str:
        return getattr(cls, "base_dir", Path(".")) / "htmlcov"

    @classmethod
    def get_log_config(
        cls, console_level: str = "INFO", **kwargs: object
    ) -> dict[str, object]:
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
        log_config = cls.get_log_config()
        if log_config["handlers"].get("file"):
            (getattr(cls, "base_dir", Path(".")) / "logs").mkdir(
                parents=True, exist_ok=True
            )

        logging.config.dictConfig(cls.get_log_config())
