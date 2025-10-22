"""Logging configuration helpers."""
from __future__ import annotations

import json
import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Any, Dict

from .config import Settings, load_settings

LOG_DIR = Path("logs")
APP_LOG_PATH = LOG_DIR / "application.log"
INGESTION_LOG_PATH = LOG_DIR / "ingestion.log"


class _JsonFormatter(logging.Formatter):
    """Lightweight JSON formatter that avoids external dependencies."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = record.stack_info
        return json.dumps(payload)


def build_logging_config(settings: Settings | None = None) -> Dict[str, Any]:
    """Return a dictionary config for logging."""

    settings = settings or load_settings()
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": f"{__name__}._JsonFormatter",
                "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
            },
            "console": {
                "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "level": "INFO",
            },
            "app_file": {
                "class": "logging.FileHandler",
                "formatter": "json",
                "level": "INFO",
                "filename": str(APP_LOG_PATH),
                "encoding": "utf-8",
                "mode": "a",
            },
            "ingestion_file": {
                "class": "logging.FileHandler",
                "formatter": "json",
                "level": "DEBUG",
                "filename": str(INGESTION_LOG_PATH),
                "encoding": "utf-8",
                "mode": "a",
            },
            "uvicorn": {
                "class": "logging.StreamHandler",
                "formatter": "console",
            },
        },
        "loggers": {
            "": {"handlers": ["default", "app_file"], "level": "INFO"},
            "uvicorn": {"handlers": ["uvicorn"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "src.ingestion": {
                "handlers": ["default", "ingestion_file", "app_file"],
                "level": "DEBUG",
                "propagate": False,
            },
            "src.ingestion.pipeline": {
                "handlers": ["default", "ingestion_file", "app_file"],
                "level": "DEBUG",
                "propagate": False,
            },
            "docling": {
                "handlers": ["default", "ingestion_file", "app_file"],
                "level": "DEBUG",
                "propagate": False,
            },
        },
    }


def setup_logging(settings: Settings | None = None) -> None:
    """Configure logging for the application."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    dictConfig(build_logging_config(settings))


__all__ = ["setup_logging", "build_logging_config"]
