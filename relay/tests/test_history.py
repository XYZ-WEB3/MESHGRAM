"""Тесты для !ping / !history команд + messages_recent helpers."""
import time

import pytest


# ── _parse_history_args ──────────────────────────────────────────────────────


def test_parse_history_args_empty(relay_module):
    """Пустые аргументы → дефолты из settings."""
    h, l = relay_module._parse_history_args("")
    assert h == relay_module.HISTORY_DEFAULT_HOURS
    assert l == relay_module.HISTORY_MAX_ITEMS


def test_parse_history_args_only_count(relay_module):
    """`!history 5` → лимит 5, часов дефолт."""
    h, l = relay_module._parse_history_args("5")
    assert h == relay_module.HISTORY_DEFAULT_HOURS
    assert l == 5


def test_parse_history_args_only_hours(relay_module):
    """`!history 3h` → 3 часа, лимит дефолт."""
    h, l = relay_module._parse_history_args("3h")
    assert h == 3
    assert l == relay_module.HISTORY_MAX_ITEMS


def test_parse_history_args_both(relay_module):
    h, l = relay_module._parse_history_args("5 3h")
    assert h == 3
    assert l == 5


def test_parse_history_args_order_irrelevant(relay_module):
    h1, l1 = relay_module._parse_history_args("3h 5")
    h2, l2 = relay_module._parse_history_args("5 3h")
    assert (h1, l1) == (h2, l2)


def test_parse_history_args_safety_caps(relay_module):
    """Защита от больших цифр — 24h max, 20 items max."""
    h, l = relay_module._parse_history_args("999h 999")
    assert h == 24
    assert l == 20


def test_parse_history_args_garbage_ignored(relay_module):
    """Левые токены не должны менять дефолты."""
    h, l = relay_module._parse_history_args("foo bar baz")
    assert h == relay_module.HISTORY_DEFAULT_HOURS
    assert l == relay_module.HISTORY_MAX_ITEMS


# ── messages_log + messages_recent_get ───────────────────────────────────────


def test_messages_log_basic(relay_with_db):
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="hello")
    rows = relay_with_db.messages_recent_get(hours=1, limit=10)
    assert len(rows) == 1
    assert rows[0]["direction"] == "in"
    assert rows[0]["slot_n"] == 1
    assert rows[0]["text"] == "hello"


def test_messages_log_skips_empty(relay_with_db):
    """Пустые тексты не попадают в БД (мусор не нужен)."""
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="")
    rows = relay_with_db.messages_recent_get(hours=1, limit=10)
    assert len(rows) == 0


def test_messages_log_truncates_at_200(relay_with_db):
    """Длинные тексты обрезаются до 200 символов в storage."""
    long_text = "x" * 500
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text=long_text)
    rows = relay_with_db.messages_recent_get(hours=1, limit=10)
    assert len(rows[0]["text"]) == 200


def test_messages_recent_get_orders_oldest_first(relay_with_db):
    """Записи в выдаче от старых к новым (естественно для чтения)."""
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="first")
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="second")
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="third")
    rows = relay_with_db.messages_recent_get(hours=1, limit=10)
    assert [r["text"] for r in rows] == ["first", "second", "third"]


def test_messages_recent_get_respects_limit(relay_with_db):
    """LIMIT N → только N последних, остальные не попадают."""
    for i in range(20):
        relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text=f"msg{i}")
    rows = relay_with_db.messages_recent_get(hours=1, limit=5)
    assert len(rows) == 5
    # Должны быть последние 5, оrdered ascending
    assert [r["text"] for r in rows] == ["msg15", "msg16", "msg17", "msg18", "msg19"]


def test_messages_recent_get_respects_hours(relay_with_db):
    """Сообщения старше cutoff не попадают."""
    # Вписываем старое (30 часов назад) — обходим helper, через прямой SQL
    old_ts = int(time.time()) - 30 * 3600
    with relay_with_db._db_lock:
        relay_with_db._db.execute(
            "INSERT INTO messages_recent (direction, slot_n, tg_user_id, text, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("in", 1, 100, "old", old_ts),
        )
        relay_with_db._db.commit()
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="new")

    # 5 часов — старое не попадёт
    rows = relay_with_db.messages_recent_get(hours=5, limit=10)
    assert [r["text"] for r in rows] == ["new"]

    # 48 часов — оба попадут
    rows = relay_with_db.messages_recent_get(hours=48, limit=10)
    assert len(rows) == 2


def test_messages_purge_old(relay_with_db):
    """Записи старше retention_days удаляются."""
    # 10 дней назад
    old_ts = int(time.time()) - 10 * 86400
    with relay_with_db._db_lock:
        relay_with_db._db.execute(
            "INSERT INTO messages_recent (direction, slot_n, tg_user_id, text, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("in", 1, 100, "very_old", old_ts),
        )
        relay_with_db._db.commit()
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="recent")

    purged = relay_with_db.messages_purge_old(retention_days=7)
    assert purged == 1
    rows = relay_with_db.messages_recent_get(hours=24 * 30, limit=100)
    assert [r["text"] for r in rows] == ["recent"]


# ── _reply_ping_payload ──────────────────────────────────────────────────────


def test_reply_ping_payload_format(relay_with_db):
    """Формат: pong slots=N up=Xs|m|h|d (с активной uptime-строкой)."""
    msg = relay_with_db._reply_ping_payload()
    assert msg.startswith("pong slots=")
    assert " up=" in msg


def test_reply_ping_payload_short_uptime(relay_with_db):
    """Свежий старт → uptime в секундах с суффиксом 's' или 'm'."""
    relay_with_db._RELAY_STARTED_AT = time.time() - 30  # 30 секунд назад
    msg = relay_with_db._reply_ping_payload()
    # 30s — должно быть 'up=30s' (или близко)
    assert "up=30s" in msg or "up=29s" in msg or "up=31s" in msg


# ── _reply_history_payload ──────────────────────────────────────────────────


def test_reply_history_empty(relay_with_db):
    """Пусто в БД → 'истор: пусто за Nh'."""
    msg = relay_with_db._reply_history_payload("")
    assert "пусто" in msg


def test_reply_history_with_messages(relay_with_db):
    """Есть сообщения → формат включает время и текст."""
    relay_with_db.messages_log("in", slot_n=1, tg_user_id=100, text="привет")
    msg = relay_with_db._reply_history_payload("")
    assert "hist" in msg
    assert "@1" in msg
    assert "привет" in msg


def test_reply_history_truncates_long(relay_with_db):
    """Длинный набор сообщений режется до MAX_TEXT_LENGTH с '...'"""
    for i in range(20):
        relay_with_db.messages_log(
            "in", slot_n=i % 5 + 1, tg_user_id=100 + i,
            text=f"длинноесообщениеномер{i}_очень_длинное_подряд",
        )
    msg = relay_with_db._reply_history_payload("24h 20")
    assert len(msg) <= relay_with_db.MAX_TEXT_LENGTH
    if len(msg) == relay_with_db.MAX_TEXT_LENGTH:
        assert msg.endswith("...")
