"""Entry point for the LoraBridge messenger."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .commands.processor import CommandProcessor
from .queue.delivery import DeliveryManager, MessageQueue
from .telegram.client import TelegramClient
from .meshtastic.client import MeshtasticClient
from .user_mapping.manager import UserMappingManager
from .utils.config import load_settings
from .utils.setup_wizard import InteractiveSetup
from .utils.logging import configure_logging


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LoraBridge messenger controller")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Запустить основной мост")
    sub.add_parser("status", help="Показать состояние модулей")
    sub.add_parser("flush", help="Очистить очереди")
    return parser


def run_bridge(base_dir: Path) -> None:
    InteractiveSetup(base_dir).ensure()
    settings = load_settings(base_dir)
    configure_logging(settings.data_dir / "logs")
    queue = MessageQueue()
    delivery = DeliveryManager(queue, settings.telegram.floodwait_threshold)
    user_mapping = UserMappingManager(settings.data_dir / "users.json", settings.history_hours)
    telegram_client = TelegramClient(queue)
    mesh_client = MeshtasticClient(queue, settings.meshtastic.throttle_interval)
    command_processor = CommandProcessor()
    command_processor.register("status", lambda ctx: "Мост активен")

    logging.getLogger(__name__).info(
        "LoraBridge initialized: %s", {
            "telegram": settings.telegram,
            "meshtastic": settings.meshtastic,
        }
    )
    # Placeholder event loop
    logging.info(
        "Очередь сообщений: outbound=%s inbound=%s",
        len(queue.outbound),
        len(queue.inbound),
    )
    delivery.should_pause()
    user_mapping.list_active_users()
    telegram_client
    mesh_client


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parents[1]

    if args.command == "run":
        run_bridge(base_dir)
    elif args.command == "status":
        InteractiveSetup(base_dir).ensure()
        settings = load_settings(base_dir)
        configure_logging(settings.data_dir / "logs")
        logging.info("Состояние: очередь=%s", settings.queue_retry_interval)
    elif args.command == "flush":
        queue = MessageQueue()
        queue.outbound.clear()
        queue.inbound.clear()
        logging.info("Очереди очищены")


if __name__ == "__main__":
    main()
