"""Queue and delivery management for LoraBridge."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

import logging


logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    payload: str
    direction: str  # "telegram" -> "meshtastic" or reverse
    user_id: str
    retries: int = 0
    created_at: datetime = datetime.now(timezone.utc)


class MessageQueue:
    """Thread-safe (coarse) queue for inbound/outbound messages."""

    def __init__(self) -> None:
        self.outbound: Deque[QueuedMessage] = deque()
        self.inbound: Deque[QueuedMessage] = deque()

    def enqueue_outbound(self, message: QueuedMessage) -> None:
        logger.info("Queueing outbound message for %s", message.user_id)
        self.outbound.append(message)

    def enqueue_inbound(self, message: QueuedMessage) -> None:
        logger.info("Queueing inbound message for %s", message.user_id)
        self.inbound.append(message)

    def next_outbound(self) -> Optional[QueuedMessage]:
        return self.outbound.popleft() if self.outbound else None

    def next_inbound(self) -> Optional[QueuedMessage]:
        return self.inbound.popleft() if self.inbound else None


class DeliveryManager:
    """Resilient delivery orchestrator."""

    def __init__(self, queue: MessageQueue, floodwait_threshold: int) -> None:
        self.queue = queue
        self.floodwait_threshold = floodwait_threshold
        self.pending_failures: Dict[str, int] = {}

    def record_failure(self, message: QueuedMessage) -> None:
        message.retries += 1
        self.pending_failures[message.user_id] = message.retries
        logger.warning(
            "Delivery failure for %s (%s) retry=%s",
            message.user_id,
            message.direction,
            message.retries,
        )
        if message.direction == "telegram":
            self.queue.enqueue_outbound(message)
        else:
            self.queue.enqueue_inbound(message)

    def should_pause(self) -> bool:
        total_pending = len(self.queue.outbound) + len(self.queue.inbound)
        flood = total_pending >= self.floodwait_threshold
        if flood:
            logger.info("FloodWait protection engaged (%s messages)", total_pending)
        return flood
