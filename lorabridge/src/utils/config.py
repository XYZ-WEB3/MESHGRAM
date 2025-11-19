"""Configuration helpers for LoraBridge."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import json
import os

from dotenv import load_dotenv


@dataclass
class TelegramSettings:
    token: str
    floodwait_threshold: int = 20


@dataclass
class MeshtasticSettings:
    serial_port: str
    baudrate: int = 115200
    throttle_interval: float = 1.5


@dataclass
class BridgeSettings:
    telegram: TelegramSettings
    meshtastic: MeshtasticSettings
    data_dir: Path
    queue_retry_interval: float = 5.0
    history_hours: int = 48


class SettingsLoader:
    """Load configuration from JSON + .env file."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.config_path = base_dir / "config" / "settings.json"
        self.env_path = base_dir / "config" / ".env"

    def load(self) -> BridgeSettings:
        load_dotenv(self.env_path)
        with self.config_path.open("r", encoding="utf-8") as handle:
            payload: Dict[str, Any] = json.load(handle)
        token = os.getenv("TELEGRAM_TOKEN", "")
        if not token:
            raise ValueError("TELEGRAM_TOKEN is not defined in .env file")
        telegram_conf = payload.get("telegram", {})
        meshtastic_conf = payload.get("meshtastic", {})
        telegram = TelegramSettings(
            token=token,
            floodwait_threshold=int(telegram_conf.get("floodwait_threshold", 20)),
        )
        meshtastic = MeshtasticSettings(
            serial_port=str(meshtastic_conf.get("serial_port", "/dev/ttyUSB0")),
            baudrate=int(meshtastic_conf.get("baudrate", 115200)),
            throttle_interval=float(meshtastic_conf.get("throttle_interval", 1.5)),
        )
        return BridgeSettings(
            telegram=telegram,
            meshtastic=meshtastic,
            data_dir=self.base_dir / "data",
            queue_retry_interval=float(payload.get("queue_retry_interval", 5.0)),
            history_hours=int(payload.get("history_hours", 48)),
        )


def load_settings(base_dir: Path | None = None) -> BridgeSettings:
    base_dir = base_dir or Path(__file__).resolve().parents[2]
    return SettingsLoader(base_dir).load()
