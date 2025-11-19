"""Command parsing for LoRa and Telegram control messages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from lorabridge.queue.manager import QueueManager
from lorabridge.user_mapping.store import UserMappingStore


@dataclass
class CommandContext:
    queue: QueueManager
    users: UserMappingStore


class CommandHandler:
    """Executes management commands received over LoRa."""

    def __init__(self, context: CommandContext):
        self.context = context
        self.commands: Dict[str, Callable[[list[str]], str]] = {
            "/ulist": self._cmd_ulist,
            "/status": self._cmd_status,
            "/flush": self._cmd_flush,
            "/help": self._cmd_help,
        }

    def handle(self, raw_text: str) -> str:
        parts = raw_text.strip().split()
        if not parts:
            return "Команда пуста"
        cmd = parts[0].lower()
        handler = self.commands.get(cmd)
        if not handler:
            return "Неизвестная команда"
        return handler(parts[1:])

    def _cmd_ulist(self, _: list[str]) -> str:
        users = self.context.users.all_active()
        if not users:
            return "Нет активных пользователей"
        return "\n".join(f"{record.mesh_id}: {record.display_name}" for record in users)

    def _cmd_status(self, _: list[str]) -> str:
        stats = self.context.queue.stats()
        return f"Очередь: in={stats['inbound']} out={stats['outbound']}"

    def _cmd_flush(self, _: list[str]) -> str:
        self.context.queue.outbound.clear()
        return "Очередь отправки очищена"

    def _cmd_help(self, _: list[str]) -> str:
        return "Доступные команды: " + ", ".join(sorted(self.commands))
