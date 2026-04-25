"""Structured logging configuration."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog
from structlog.stdlib import BoundLogger

DEFAULT_LOG_FILE = Path("data/logs/andyjuan.jsonl")
_CONFIG_SIGNATURE: tuple[str, str] | None = None


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a configured structlog logger."""

    log_file = Path(os.getenv("LOG_FILE", str(DEFAULT_LOG_FILE)))
    app_env = os.getenv("APP_ENV", "dev").lower()
    signature = (str(log_file), app_env)

    global _CONFIG_SIGNATURE
    if _CONFIG_SIGNATURE != signature:
        _configure_logging(log_file, app_env)
        _CONFIG_SIGNATURE = signature

    logger_name = "andyjuan" if name is None else f"andyjuan.{name}"
    return structlog.get_logger(logger_name)


def _configure_logging(log_file: Path, app_env: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("andyjuan")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(message)s")
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if app_env == "dev":
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
