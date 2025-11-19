"""Logging helpers with rotating logs."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "bridge.log"
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])
