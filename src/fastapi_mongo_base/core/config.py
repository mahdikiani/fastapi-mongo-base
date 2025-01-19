"""FastAPI server configuration."""

import dataclasses
import logging
import logging.config
import os

import dotenv
from singleton import Singleton

dotenv.load_dotenv()


@dataclasses.dataclass
class Settings(metaclass=Singleton):
    """Server config settings."""

    # base_dir: Path = Path(__file__).resolve().parent.parent
    root_url: str = os.getenv("DOMAIN", default="http://localhost:8000")
    project_name: str = os.getenv("PROJECT_NAME", default="PROJECT")
    base_path: str = "/api/v1"
    worker_update_time: int = int(os.getenv("WORKER_UPDATE_TIME", default=180))
    testing: bool = os.getenv("DEBUG", default=False)

    page_max_limit: int = 100

    mongo_uri: str = os.getenv("MONGO_URI", default="mongodb://localhost:27017/")
    redis_uri: str = os.getenv("REDIS_URI", default="redis://localhost:6379/0")

    app_id: str = os.getenv("APP_ID")
    app_secret: str = os.getenv("APP_SECRET")

    JWT_CONFIG: str = os.getenv(
        "USSO_JWT_CONFIG",
        default='{"jwk_url": "https://sso.usso.io/website/jwks.json","type": "RS256","header": {"type": "Cookie", "name": "usso_access_token"} }',
    )

    @classmethod
    def get_coverage_dir(cls):
        return cls.base_dir / "htmlcov"

    @classmethod
    def get_log_config(
        cls, console_level: str = "INFO", file_level: str = "INFO", **kwargs
    ):
        log_config = {
            "formatters": {
                "standard": {
                    "format": "[{levelname} : {filename}:{lineno} : {asctime} -> {funcName:10}] {message}",
                    "style": "{",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": console_level,
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "level": file_level,
                    "filename": cls.base_dir / "logs" / "info.log",
                    "formatter": "standard",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": "INFO",
                    "propagate": True,
                },
                "httpx": {
                    "handlers": ["console", "file"],
                    "level": "WARNING",
                    "propagate": False,
                },
            },
            "version": 1,
        }
        return log_config

    @classmethod
    def config_logger(cls):
        (cls.base_dir / "logs").mkdir(parents=True, exist_ok=True)

        logging.config.dictConfig(cls.get_log_config())
