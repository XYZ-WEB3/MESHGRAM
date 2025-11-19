"""Telegram integration for LoraBridge Messenger."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from lorabridge.queue.manager import QueuedMessage, QueueManager
from lorabridge.user_mapping.store import UserMappingStore

LOGGER = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    telegram_id: int
    display_name: str
    text: str


class TelegramClient:
    """Simplified async interface used by the service."""

    def __init__(
        self,
        queue: QueueManager,
        users: UserMappingStore,
        notifier: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        self.queue = queue
        self.users = users
        self.notifier = notifier
        self._running = False

    async def start(self) -> None:
        LOGGER.info("Telegram client started (mock mode)")
        self._running = True

    async def stop(self) -> None:
        LOGGER.info("Telegram client stopped")
        self._running = False

    async def handle_incoming(self, message: TelegramMessage) -> str:
        """Process a new Telegram message and enqueue it for LoRa delivery."""

        record = self.users.assign(message.telegram_id, message.display_name)
        queued = QueuedMessage(user_id=record.mesh_id, payload=message.text)
        await self.queue.enqueue_outbound(queued)
        LOGGER.info("Запрос от %s поставлен в очередь как %s", message.display_name, record.mesh_id)
        return record.mesh_id

    async def notify_buffered(self, telegram_id: int) -> None:
        if not self.notifier:
            return
        await self.notifier("Сообщение доставлено в буфер, отправлю при появлении связи.")

    async def deliver_response(self, record: UserMappingStore, text: str) -> None:  # type: ignore[arg-type]
        # In the MVP we just log the behavior.
        LOGGER.info("Delivering message to %s: %s", record.mesh_id, text)
