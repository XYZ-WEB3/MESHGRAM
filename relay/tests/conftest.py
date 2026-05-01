"""
pytest конфиг для relay/tests/.

- Добавляет relay/ в sys.path
- Фикстура `relay_module` грузит relay.py один раз на сессию
- Фикстура `relay_with_db` создаёт in-memory SQLite c полной схемой
  и подменяет relay._db перед тестом, восстанавливает после
"""
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_RELAY_DIR = Path(__file__).resolve().parent.parent
if str(_RELAY_DIR) not in sys.path:
    sys.path.insert(0, str(_RELAY_DIR))


@pytest.fixture(scope="session")
def relay_module():
    """Загружает relay.py один раз на сессию.

    relay.py при импорте читает .env через settings.load() — но не
    подключается к meshtastic-ноде и не дёргает Telegram, поэтому
    импорт безопасен. Если .env нет — settings.load() возвращает дефолты.
    """
    import logging
    logging.disable(logging.CRITICAL)
    spec = importlib.util.spec_from_file_location(
        "relay", str(_RELAY_DIR / "relay.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def relay_with_db(relay_module):
    """Подменяет relay._db на свежую in-memory БД с полной схемой.

    Каждый тест получает чистую БД. После теста — закрываем и возвращаем
    оригинал на место (хотя обычно тесты в одном процессе работают только
    с in-memory; всё равно бережно).
    """
    original_db = getattr(relay_module, "_db", None)
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    relay_module._db = db
    with relay_module._db_lock:
        db.executescript(relay_module._DB_SCHEMA)
        db.commit()
    try:
        yield relay_module
    finally:
        try:
            db.close()
        except Exception:
            pass
        relay_module._db = original_db
