"""Interactive onboarding wizard for LoraBridge."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import json

from dotenv import dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt


def _detect_serial_ports() -> List[str]:
    """Return detected serial ports if pyserial is available."""

    try:
        from serial.tools import list_ports  # type: ignore

        return [port.device for port in list_ports.comports()]
    except Exception:  # pragma: no cover - optional dependency
        return []


def _ask_int(console: Console, message: str, default: int) -> int:
    while True:
        raw = Prompt.ask(message, default=str(default))
        try:
            return int(raw)
        except ValueError:
            console.print("[red]Введите целое число[/red]")


def _ask_float(console: Console, message: str, default: float) -> float:
    while True:
        raw = Prompt.ask(message, default=str(default))
        try:
            return float(raw)
        except ValueError:
            console.print("[red]Введите число[/red]")


DEFAULT_SETTINGS: Dict[str, object] = {
    "telegram": {"floodwait_threshold": 20},
    "meshtastic": {
        "serial_port": "/dev/ttyUSB0",
        "baudrate": 115200,
        "throttle_interval": 1.5,
    },
    "queue_retry_interval": 5.0,
    "history_hours": 48,
}


@dataclass
class InteractiveSetup:
    """Guide the operator through Telegram login and hardware selection."""

    base_dir: Path

    def __post_init__(self) -> None:
        self.console = Console()
        self.env_path = self.base_dir / "config" / ".env"
        self.settings_path = self.base_dir / "config" / "settings.json"

    def ensure(self) -> None:
        """Run the wizard when required or when the operator requests it."""

        token = self._current_token()
        settings = self._load_settings()
        if token and settings:
            self.console.print(
                Panel.fit(
                    "Обнаружена готовая конфигурация. Телеграм‑бот и COM-порт уже настроены.",
                    title="LoraBridge",
                    style="green",
                )
            )
            if Confirm.ask("Оставить текущие параметры?", default=True):
                return
        self._run_wizard(settings, token)

    def _run_wizard(self, defaults: Dict[str, object], token: str | None) -> None:
        self.console.print(
            Panel.fit(
                "Настроим Telegram-бота, выберем COM-порт и сохраним параметры.",
                title="Мастер настройки",
            )
        )
        new_token = self._ask_token(token)
        floodwait = _ask_int(
            self.console,
            "Лимит FloodWait (секунд ожидания перед паузой очереди)",
            default=int(self._nested(defaults, ["telegram", "floodwait_threshold"], 20)),
        )
        serial_port = self._ask_serial_port(
            str(self._nested(defaults, ["meshtastic", "serial_port"], "/dev/ttyUSB0"))
        )
        baudrate = _ask_int(
            self.console,
            "Скорость (baudrate) Meshtastic",
            default=int(self._nested(defaults, ["meshtastic", "baudrate"], 115200)),
        )
        throttle = _ask_float(
            self.console,
            "Интервал отправки в UART (сек)",
            default=float(self._nested(defaults, ["meshtastic", "throttle_interval"], 1.5)),
        )
        retry_interval = _ask_float(
            self.console,
            "Интервал повторной отправки очереди (сек)",
            default=float(defaults.get("queue_retry_interval", 5.0)),
        )
        history_hours = _ask_int(
            self.console,
            "Сколько часов хранить историю ID",
            default=int(defaults.get("history_hours", 48)),
        )

        payload = {
            "telegram": {"floodwait_threshold": floodwait},
            "meshtastic": {
                "serial_port": serial_port,
                "baudrate": baudrate,
                "throttle_interval": throttle,
            },
            "queue_retry_interval": retry_interval,
            "history_hours": history_hours,
        }
        self._write_env(new_token)
        self._write_settings(payload)
        self.console.print("[green]Параметры сохранены. Можно запускать мост.[/green]")

    def _ask_token(self, token: str | None) -> str:
        message = "Введите токен Telegram-бота"
        while True:
            value = Prompt.ask(message, default=token or "", password=True).strip()
            if value:
                return value
            self.console.print("[red]Токен обязателен[/red]")

    def _ask_serial_port(self, default: str) -> str:
        ports = _detect_serial_ports()
        if not ports:
            return Prompt.ask("COM-порт Meshtastic", default=default)

        self.console.print("Доступные порты:")
        for idx, port in enumerate(ports, start=1):
            self.console.print(f"  [bold]{idx}[/bold] {port}")
        self.console.print("  [bold]0[/bold] Ввести вручную")
        while True:
            choice = Prompt.ask("Выберите номер", default="1")
            if choice == "0":
                return Prompt.ask("COM-порт Meshtastic", default=default)
            try:
                idx = int(choice)
            except ValueError:
                self.console.print("[red]Введите номер из списка[/red]")
                continue
            if 1 <= idx <= len(ports):
                return ports[idx - 1]
            self.console.print("[red]Нет такого номера[/red]")

    def _write_env(self, token: str) -> None:
        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(f"TELEGRAM_TOKEN={token}\n", encoding="utf-8")

    def _write_settings(self, payload: Dict[str, object]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def _current_token(self) -> str | None:
        if not self.env_path.exists():
            return None
        env = dotenv_values(self.env_path)
        token = env.get("TELEGRAM_TOKEN")
        return token if token else None

    def _load_settings(self) -> Dict[str, object]:
        if not self.settings_path.exists():
            return DEFAULT_SETTINGS.copy()
        try:
            with self.settings_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError:
            return DEFAULT_SETTINGS.copy()
        merged: Dict[str, object] = json.loads(json.dumps(DEFAULT_SETTINGS))
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)  # type: ignore[index]
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _nested(data: Dict[str, object], keys: List[str], default: object) -> object:
        current: object = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]  # type: ignore[assignment]
            else:
                return default
        return current
