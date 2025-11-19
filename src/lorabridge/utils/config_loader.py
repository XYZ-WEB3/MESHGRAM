"""Utilities for loading service configuration from JSON and environment files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import json
import os

from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv


class TelegramSettings(BaseModel):
    """Configuration for the Telegram integration."""

    bot_token: str = Field(..., description="Bot token from @BotFather")
    admin_usernames: list[str] = Field(default_factory=list)
    floodwait_padding: int = Field(5, description="Seconds to wait after hitting FloodWait")


class MeshtasticSettings(BaseModel):
    """Configuration for the Meshtastic serial connection."""

    serial_port: str = Field(..., description="Serial interface of the device, e.g. /dev/ttyUSB0")
    baudrate: int = Field(921600, description="Serial speed for the modem")
    channel: str = Field("LongFast", description="Meshtastic channel name")
    throttle_seconds: float = Field(2.5, description="Delay between LoRa transmissions")


class QueueSettings(BaseModel):
    """Queue configuration shared across the service."""

    max_retries: int = 5
    retry_delay: int = 15
    inbound_limit: int = 100
    outbound_limit: int = 100


class StorageSettings(BaseModel):
    """Settings describing persistent storage locations."""

    users_path: Path = Field(Path("data/users.json"))
    logs_dir: Path = Field(Path("data/logs"))


class ServiceSettings(BaseModel):
    """Top-level settings loaded from the JSON file."""

    telegram: TelegramSettings
    meshtastic: MeshtasticSettings
    queue: QueueSettings = QueueSettings()
    storage: StorageSettings = StorageSettings()


@dataclass(slots=True)
class LoadedSettings:
    """Bundle that contains parsed settings and resolved paths."""

    settings: ServiceSettings
    settings_path: Path


def load_settings(settings_path: str | Path) -> LoadedSettings:
    """Load JSON settings from disk and validate them."""

    path = Path(settings_path)
    if not path.exists():
        raise FileNotFoundError(f"Settings file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        payload: Dict[str, Any] = json.load(handle)

    try:
        parsed = ServiceSettings(**payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid configuration: {exc}") from exc

    return LoadedSettings(settings=parsed, settings_path=path)


def load_environment(env_path: str | Path = "config/.env") -> None:
    """Load environment variables so tokens are not hard coded."""

    path = Path(env_path)
    load_dotenv(path)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        # Allow overriding the JSON file when secrets live in the env.
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", os.environ["TELEGRAM_BOT_TOKEN"])
