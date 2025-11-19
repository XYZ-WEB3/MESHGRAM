"""Meshtastic connectivity for the bridge."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from lorabridge.commands.handler import CommandContext, CommandHandler
from lorabridge.queue.manager import QueuedMessage, QueueManager
from lorabridge.user_mapping.store import UserMappingStore

LOGGER = logging.getLogger(__name__)


@dataclass
class MeshPacket:
    sender: str
    text: str


class MeshtasticClient:
    """Simplified async interface that mimics serial behavior."""

    def __init__(
        self,
        queue: QueueManager,
        users: UserMappingStore,
        dispatcher: Callable[[str, str], Awaitable[None]],
        command_handler: CommandHandler,
        throttle_seconds: float = 2.5,
    ):
        self.queue = queue
        self.users = users
        self.dispatcher = dispatcher
        self.command_handler = command_handler
        self.throttle_seconds = throttle_seconds
        self._running = False

    async def start(self) -> None:
        LOGGER.info("Meshtastic client ready (mock mode)")
        self._running = True
        asyncio.create_task(self._pump_outbound())

    async def stop(self) -> None:
        self._running = False

    async def _pump_outbound(self) -> None:
        while self._running:
            message = await self.queue.get_next_outbound()
            if message:
                await asyncio.sleep(self.throttle_seconds)
                await self.send_text(message.user_id, message.payload)
                await self.queue.mark_outbound_delivered()
            await asyncio.sleep(0.1)

    async def send_text(self, mesh_id: str, text: str) -> None:
        LOGGER.info("Sending to %s via Meshtastic: %s", mesh_id, text)

    async def handle_packet(self, packet: MeshPacket) -> None:
        text = packet.text.strip()
        if text.startswith("/"):
            response = self.command_handler.handle(text)
            await self.dispatcher(packet.sender, response)
            return
        if not text.startswith("#"):
            LOGGER.warning("Invalid payload received: %s", text)
            return
        parts = text.split(maxsplit=1)
        mesh_id = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        record = self.users.find_by_mesh_id(mesh_id)
        if not record:
            LOGGER.warning("Unknown mesh id %s", mesh_id)
            return
        await self.dispatcher(record.mesh_id, body)
