"""Telegram module placeholder implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import logging

from ..queue.delivery import MessageQueue, QueuedMessage


logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    telegram_id: int
    text: str


class TelegramClient:
    """Simplified Telegram client abstraction."""

    def __init__(self, queue: MessageQueue) -> None:
        self.queue = queue

    def handle_incoming(self, messages: Iterable[TelegramMessage]) -> None:
        for message in messages:
            logger.info("Received Telegram message %s", message.telegram_id)
            queued = QueuedMessage(
                payload=message.text,
                direction="telegram",
                user_id=str(message.telegram_id),
            )
            self.queue.enqueue_outbound(queued)

    def deliver_response(self, queued: QueuedMessage) -> None:
        logger.info("Delivering message %s back to Telegram", queued.user_id)
        # Placeholder for integration with python-telegram-bot
