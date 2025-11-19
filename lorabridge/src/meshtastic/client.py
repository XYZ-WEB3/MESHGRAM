"""Meshtastic module placeholder implementation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import logging

from ..queue.delivery import MessageQueue, QueuedMessage


logger = logging.getLogger(__name__)


@dataclass
class MeshMessage:
    mesh_id: str
    text: str


class MeshtasticClient:
    """Simplified Meshtastic serial client."""

    def __init__(self, queue: MessageQueue, throttle_interval: float = 1.5) -> None:
        self.queue = queue
        self.throttle_interval = throttle_interval

    def handle_incoming(self, messages: Iterable[MeshMessage]) -> None:
        for message in messages:
            logger.info("Received LoRa message %s", message.mesh_id)
            queued = QueuedMessage(
                payload=message.text,
                direction="meshtastic",
                user_id=message.mesh_id,
            )
            self.queue.enqueue_inbound(queued)

    def deliver_to_mesh(self, queued: QueuedMessage) -> None:
        logger.info(
            "Delivering message %s to Meshtastic with throttling=%s",
            queued.user_id,
            self.throttle_interval,
        )
        # Placeholder for serial write
