"""LoRa command processor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass
class CommandContext:
    user_id: str
    args: List[str]


class CommandProcessor:
    """Simple registry for mesh commands."""

    def __init__(self) -> None:
        self.commands: Dict[str, Callable[[CommandContext], str]] = {}

    def register(self, name: str, handler: Callable[[CommandContext], str]) -> None:
        self.commands[name.lower()] = handler

    def process(self, raw: str, user_id: str) -> str | None:
        if not raw.startswith("/"):
            return None
        parts = raw.split()
        command = parts[0][1:].lower()
        args = parts[1:]
        handler = self.commands.get(command)
        if not handler:
            return "Неизвестная команда, используйте /help"
        context = CommandContext(user_id=user_id, args=args)
        return handler(context)
