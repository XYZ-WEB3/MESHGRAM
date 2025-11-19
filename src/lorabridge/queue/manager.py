"""Queue management primitives shared by Telegram and Meshtastic modules."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Optional


@dataclass
class QueuedMessage:
    """Represents a message waiting for delivery."""

    user_id: str
    payload: str
    retries: int = 0
    last_attempt: Optional[datetime] = None


class QueueManager:
    """Coordinates inbound/outbound queues and retry logic."""

    def __init__(self, inbound_limit: int = 100, outbound_limit: int = 100, retry_delay: int = 15):
        self.outbound: Deque[QueuedMessage] = deque(maxlen=outbound_limit)
        self.inbound: Deque[QueuedMessage] = deque(maxlen=inbound_limit)
        self.retry_delay = timedelta(seconds=retry_delay)
        self._lock = asyncio.Lock()

    async def enqueue_outbound(self, message: QueuedMessage) -> None:
        async with self._lock:
            self.outbound.append(message)

    async def enqueue_inbound(self, message: QueuedMessage) -> None:
        async with self._lock:
            self.inbound.append(message)

    async def get_next_outbound(self) -> Optional[QueuedMessage]:
        async with self._lock:
            if not self.outbound:
                return None
            message = self.outbound[0]
            if message.last_attempt and datetime.utcnow() - message.last_attempt < self.retry_delay:
                return None
            message.last_attempt = datetime.utcnow()
            return message

    async def mark_outbound_delivered(self) -> None:
        async with self._lock:
            if self.outbound:
                self.outbound.popleft()

    async def bump_retry(self) -> None:
        async with self._lock:
            if not self.outbound:
                return
            self.outbound[0].retries += 1

    def stats(self) -> dict[str, int]:
        return {
            "inbound": len(self.inbound),
            "outbound": len(self.outbound),
        }
