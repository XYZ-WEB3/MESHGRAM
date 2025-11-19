"""Centralized logging helpers with rotating file handlers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(logs_dir: str | Path, verbose: bool = False) -> None:
    """Configure logging for console and rotating file output."""

    path = Path(logs_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / "lorabridge.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    console.setLevel(logging.INFO)
    root_logger.addHandler(console)

    rotating_handler = RotatingFileHandler(log_file, maxBytes=1024 * 1024, backupCount=5)
    rotating_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    rotating_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(rotating_handler)
