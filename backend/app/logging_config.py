from __future__ import annotations

import logging
from logging.config import dictConfig

LOG_FORMAT = "%(levelprefix)s %(message)s"


def configure_logging(level: str = "INFO", *, use_colors: bool | None = None) -> None:
    """Configure logging so app output matches uvicorn's default style."""

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    formatter_config: dict[str, object] = {
        "()": "uvicorn.logging.DefaultFormatter",
        "fmt": LOG_FORMAT,
    }
    if use_colors is not None:
        formatter_config["use_colors"] = use_colors

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "uvicorn": formatter_config,
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "uvicorn",
                }
            },
            "root": {
                "handlers": ["default"],
                "level": normalized_level,
            },
        }
    )
