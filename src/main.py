"""Entry point for LoraBridge Messenger."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import click

from lorabridge.commands.handler import CommandContext, CommandHandler
from lorabridge.meshtastic.client import MeshtasticClient
from lorabridge.queue.manager import QueueManager
from lorabridge.telegram.client import TelegramClient
from lorabridge.user_mapping.store import UserMappingStore
from lorabridge.utils.config_loader import load_environment, load_settings
from lorabridge.utils.logging_setup import setup_logging

LOGGER = logging.getLogger(__name__)


@dataclass
class ServiceContext:
    queue: QueueManager
    telegram: TelegramClient
    meshtastic: MeshtasticClient
    users: UserMappingStore


async def run_service(settings_path: Path, verbose: bool) -> None:
    loaded = load_settings(settings_path)
    load_environment()
    setup_logging(loaded.settings.storage.logs_dir, verbose=verbose)

    queue = QueueManager(
        inbound_limit=loaded.settings.queue.inbound_limit,
        outbound_limit=loaded.settings.queue.outbound_limit,
        retry_delay=loaded.settings.queue.retry_delay,
    )
    users = UserMappingStore(loaded.settings.storage.users_path)
    command_handler = CommandHandler(CommandContext(queue=queue, users=users))

    async def dispatcher(mesh_id: str, text: str) -> None:
        LOGGER.info("Dispatching response to %s: %s", mesh_id, text)

    telegram_client = TelegramClient(queue=queue, users=users)
    meshtastic_client = MeshtasticClient(
        queue=queue,
        users=users,
        dispatcher=dispatcher,
        command_handler=command_handler,
        throttle_seconds=loaded.settings.meshtastic.throttle_seconds,
    )
    await telegram_client.start()
    await meshtastic_client.start()
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await telegram_client.stop()
        await meshtastic_client.stop()


@click.group()
def cli() -> None:
    """CLI interface for LoraBridge Messenger."""


@cli.command()
@click.option("--settings", type=click.Path(path_type=Path), default=Path("config/settings.json"))
@click.option("--verbose", is_flag=True, help="Enable debug logging")
def run(settings: Path, verbose: bool) -> None:
    """Start the asynchronous bridge."""

    asyncio.run(run_service(settings, verbose))


@cli.command("show-users")
@click.option("--settings", type=click.Path(path_type=Path), default=Path("config/settings.json"))
def show_users(settings: Path) -> None:
    """Print active mappings."""

    loaded = load_settings(settings)
    users = UserMappingStore(loaded.settings.storage.users_path)
    for record in users.all_active():
        click.echo(f"{record.mesh_id}\t{record.display_name}\t{record.last_seen.isoformat()}")


if __name__ == "__main__":
    cli()
