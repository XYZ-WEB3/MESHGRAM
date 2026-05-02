#!/usr/bin/env python3
"""
Public Telegram -> Meshtastic relay.

Flow:
  * Public Telegram user writes to the bot.
  * The bot assigns a slot number @N, formats the packet as
    "[@N user HH:MM] text" and sends it as a Meshtastic DM
    to the pocket node (encrypted peer-to-peer).
  * Mikhail reads on the pocket node and answers with
    "@N my reply" (or "@N !ban" to block the user).
  * That mesh message comes back over LoRa, the bot parses it
    and DMs the original Telegram user with the reply.

Slot rules:
  * Each incoming user message gets its own slot with a 20h TTL.
  * When Mikhail replies with "@N ..." the slot is freed immediately.
  * Expired slots are garbage-collected every minute.
  * Freed numbers are reused (lowest free first).

Owner mode:
  * When the user with id OWNER_ID writes to the bot, their message
    is sent as a DM to the pocket node unchanged (prefixed "[admin]")
    and not routed through the slot system. Useful for testing.
  * Commands /nodes /slots /dm /broadcast /ban /unban /banlist are
    available only to the owner.

Privacy:
  * Uses Meshtastic DMs (destinationId=POCKET_NODE_ID). Payload is
    end-to-end encrypted between home and pocket; other mesh nodes
    relay the encrypted blob but cannot read it.
  * If you want full channel isolation (other nodes do not even see
    metadata), create a private channel in the Meshtastic app on
    both devices. That is device-side config, not a code change.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import queue
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import meshtastic
import meshtastic.serial_interface
from pubsub import pub
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import Conflict, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===== Auto-restart / polling resiliency =====
# Сколько ждать перед первым перезапуском после сетевой ошибки в Telegram.
# Каждый следующий fail удваивает задержку, capped POLLING_RESTART_MAX_SEC.
# Если бот проработал стабильно >= POLLING_STABLE_RESET_SEC — сбрасываем
# backoff к initial. Это чтобы редкий разовый NetworkError не раскручивал
# задержку до 5 минут.
POLLING_RESTART_INITIAL_SEC: int = 5
POLLING_RESTART_MAX_SEC:     int = 300
POLLING_STABLE_RESET_SEC:    int = 60

# ============================================================
# CONFIG — loaded from .env via settings.py (edit via GUI)
# ============================================================
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))
import ai_helper
import paths as _paths
import settings as _settings_mod

_S = _settings_mod.load()

BOT_TOKEN: str        = _S["bot_token"]
OWNER_ID: int         = int(_S["owner_id"]) if _S["owner_id"] else 0
POCKET_NODE_ID: str   = _S["pocket_node_id"]
DISPLAY_NAME: str     = (_S.get("display_name") or "Михаил").strip()

# Serial port: CLI flag (--port) wins; otherwise the GUI's last-used.
MESHTASTIC_PORT: Optional[str] = (_S.get("last_com_port") or None)

MAX_TEXT_LENGTH: int        = int(_S["max_text_length"])
SLOT_TTL_HOURS: int         = int(_S["slot_ttl_hours"])
SLOT_STICKY_HOURS: int      = int(_S["slot_sticky_hours"])
MAX_USERNAME_IN_PREFIX: int = int(_S["max_username_in_prefix"])

POCKET_FRESH_MIN: int = int(_S["pocket_fresh_min"])
POCKET_STALE_MIN: int = int(_S["pocket_stale_min"])

GPS_ENABLED: bool          = bool(_S["gps_enabled"])
GPS_FIX_FRESH_MIN: int     = int(_S["gps_fix_fresh_min"])
GPS_FIX_STALE_MIN: int     = int(_S["gps_fix_stale_min"])
GPS_FIX_MAX_MIN: int       = int(_S["gps_fix_max_min"])
WHERE_RATE_LIMIT_MIN: int  = int(_S["where_rate_limit_min"])

WHITELIST_ENABLED: bool = bool(_S["whitelist_enabled"])

SOS_ENABLED: bool         = bool(_S["sos_enabled"])
SOS_RECIPIENTS: list[int] = [int(x) for x in (_S["sos_recipients"] or [])]
SOS_MESSAGE: str          = str(_S["sos_message"])
SOS_INCLUDE_COORDS: bool  = bool(_S["sos_include_coords"])

RETRY_INITIAL_DELAY_MIN: int = int(_S["retry_initial_delay_min"])
RETRY_MAX_INTERVAL_MIN: int  = int(_S["retry_max_interval_min"])

# Mesh: hop_limit на исходящих DM. 1 = direct only (без retransmit'ов через
# другие ноды). Подходит для ближних случаев и снимает 5–15 с ожидания
# окна ретрансляции. Поднять в .env (MESH_HOP_LIMIT=3) если pocket-нода
# может оказаться за пределами прямой видимости.
MESH_HOP_LIMIT: int = int(_S["mesh_hop_limit"])

# Режим доставки. "reliable" — wantAck=True, ретраи, статусы доставки.
# "fast" — wantAck=False, fire-and-forget: мгновенно, без подтверждения.
MESH_DELIVERY_MODE: str = str(_S.get("mesh_delivery_mode") or "reliable").lower()
if MESH_DELIVERY_MODE not in ("reliable", "fast"):
    MESH_DELIVERY_MODE = "reliable"
MESH_WANT_ACK: bool = (MESH_DELIVERY_MODE == "reliable")

# AI helper. Активируется через AI_ENABLED=true и работает с любым
# OpenAI-совместимым endpoint'ом (LM Studio, Ollama, vLLM, OpenAI cloud).
AI_ENABLED: bool         = bool(_S.get("ai_enabled", False))
AI_BASE_URL: str         = str(_S.get("ai_base_url") or "http://localhost:1234/v1")
AI_API_KEY: str          = str(_S.get("ai_api_key") or "lm-studio")
AI_MODEL: str            = str(_S.get("ai_model") or "llama-3.2-8b-instruct")
AI_SYSTEM_PROMPT: str    = str(_S.get("ai_system_prompt") or
                               "Отвечай коротко и ясно. Максимум 2-3 предложения.")
AI_TIMEOUT_SEC: int      = int(_S.get("ai_timeout_sec") or 30)
AI_MAX_HISTORY: int      = int(_S.get("ai_max_history") or 10)
AI_TTL_HOURS: int        = int(_S.get("ai_ttl_hours") or 168)

# SQLite file next to this script.
# DB лежит рядом с пользовательским .env. В frozen .exe — рядом с .exe,
# в source — рядом с relay.py. См. paths.py для обоснования.
DB_PATH: Path = _paths.APP_DATA_DIR / "relay.db"

# Лог-файл рядом со скриптом. Ротация по размеру: при достижении
# LOG_FILE_MAX_MB файл переименовывается в .1 (старый .1 → .2 и т.д.),
# хранится LOG_FILE_KEEP бэкапов. Настраивается в .env.
LOG_FILE_PATH:    Path = _paths.APP_DATA_DIR / "relay.log"
LOG_FILE_ENABLED: bool = bool(_S["log_file_enabled"])
LOG_FILE_MAX_MB:  int  = int(_S["log_file_max_mb"])
LOG_FILE_KEEP:    int  = int(_S["log_file_keep"])

# ============================================================

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _setup_logging() -> None:
    """Ставим stdout-handler через basicConfig + (опционально) ротируемый
    файловый. httpx/telegram-логгеры приглушены до WARNING — иначе
    polling спамит DEBUG/INFO про каждый getUpdates."""
    logging.basicConfig(format=_LOG_FORMAT, level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    if not LOG_FILE_ENABLED:
        return
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            LOG_FILE_PATH,
            maxBytes=max(1, LOG_FILE_MAX_MB) * 1024 * 1024,
            backupCount=max(0, LOG_FILE_KEEP),
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter(_LOG_FORMAT))
        fh.setLevel(logging.INFO)
        logging.getLogger().addHandler(fh)
    except OSError as e:
        # Если не можем писать в файл (read-only fs / permission),
        # продолжаем с одним только stdout. Не падаем.
        logging.getLogger().warning(
            "File logging disabled: cannot open %s (%s)", LOG_FILE_PATH, e,
        )


_setup_logging()
log = logging.getLogger("relay")


# ============================================================
# Global state
# ============================================================
_mesh_iface: Optional[meshtastic.serial_interface.SerialInterface] = None
_my_node_num: Optional[int] = None
_my_node_id: Optional[str] = None
_pocket_last_heard: Optional[float] = None  # unix seconds

# SQLite is touched from both the asyncio loop and the meshtastic
# background thread — serialise with a lock.
_db_lock = threading.Lock()
_db: Optional[sqlite3.Connection] = None

# Mesh -> asyncio queue. The meshtastic callback is in its own thread
# and must not touch the event loop directly.
_mesh_queue: "queue.Queue[dict]" = queue.Queue()

# In-memory rate limit for /where: {tg_user_id: last_request_unix_ts}.
# Cleared on restart; that is acceptable for spam control.
_where_last_call: dict[int, float] = {}


# ============================================================
# SQLite layer
# ============================================================
_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_user_id  INTEGER PRIMARY KEY,
    tg_username TEXT,
    first_name  TEXT,
    banned      INTEGER NOT NULL DEFAULT 0,
    whitelisted INTEGER NOT NULL DEFAULT 0,
    entry_tag   TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS slots (
    slot_n       INTEGER PRIMARY KEY,
    tg_user_id   INTEGER NOT NULL,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL,
    was_replied  INTEGER NOT NULL DEFAULT 0,
    last_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_slots_expires ON slots(expires_at);
CREATE INDEX IF NOT EXISTS idx_slots_user    ON slots(tg_user_id);

-- Referral categories for /link deeplinks (t.me/bot?start=<tag>).
CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    tag        TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);

-- GPS / location sharing (BETA)
CREATE TABLE IF NOT EXISTS favorites (
    tg_user_id INTEGER PRIMARY KEY,
    added_at   INTEGER NOT NULL,
    note       TEXT
);

-- Singleton row (id=1) holding the latest known position of POCKET_NODE_ID.
CREATE TABLE IF NOT EXISTS gps_position (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    alt         REAL,
    fix_time    INTEGER,
    received_at INTEGER NOT NULL
);

-- Delivery retry queue (TASK-2).
-- is_sos=1 → fast-retry (5/15/30/60/120 сек) для срочных сообщений
-- (юзер написал «#SOS» / «срочно» / «urgent» в тексте).
CREATE TABLE IF NOT EXISTS retry_queue (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_user_id     INTEGER NOT NULL,
    tg_chat_id     INTEGER NOT NULL,
    status_msg_id  INTEGER NOT NULL,
    slot_n         INTEGER NOT NULL,
    payload        TEXT NOT NULL,
    attempts       INTEGER NOT NULL DEFAULT 0,
    next_try_at    INTEGER NOT NULL,
    deadline       INTEGER NOT NULL,
    is_sos         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_retry_next ON retry_queue(next_try_at);
CREATE INDEX IF NOT EXISTS idx_retry_slot ON retry_queue(slot_n);

-- AI helper: чаты с локальной/облачной LLM, инициируются с pocket
-- командой «@ai <вопрос>», продолжаются как «@aiN <вопрос>».
CREATE TABLE IF NOT EXISTS ai_conversations (
    slot_n_ai     INTEGER PRIMARY KEY,
    created_at    INTEGER NOT NULL,
    last_used_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_n_ai     INTEGER NOT NULL,
    role          TEXT NOT NULL,    -- 'user' / 'assistant' (system промпт идёт из настроек, не хранится)
    content       TEXT NOT NULL,
    ts            INTEGER NOT NULL,
    FOREIGN KEY (slot_n_ai) REFERENCES ai_conversations(slot_n_ai) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_aimsg_slot ON ai_messages(slot_n_ai);
CREATE INDEX IF NOT EXISTS idx_aimsg_ts   ON ai_messages(ts);
"""


# SOS fast-retry — для срочных сообщений (#SOS / срочно / urgent в тексте).
# Шаги: 5 → 15 → 30 → 60 → 120 секунд (вместо стандартных 2-15 минут).
_RETRY_SOS_BACKOFF_SEC = (5, 15, 30, 60, 120)
_RE_URGENT = re.compile(r"#SOS\b|\b(?:срочно|urgent|emergency)\b", re.IGNORECASE)


def _is_urgent(text: str) -> bool:
    """True если текст содержит SOS-маркер. Триггерит fast-retry."""
    return bool(_RE_URGENT.search(text or ""))


def _now() -> int:
    return int(time.time())


def db_init() -> None:
    global _db
    _db = sqlite3.connect(DB_PATH, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    with _db_lock:
        # WAL: одновременные read'ы не блокируют пишущего, и наоборот.
        # Под нашу нагрузку (один Михаил, retry_worker, expiry_worker, GUI
        # пишет users/banlist) — снимает риск "database is locked".
        # synchronous=NORMAL — стандартный безопасный компромисс для WAL.
        _db.execute("PRAGMA journal_mode=WAL;")
        _db.execute("PRAGMA synchronous=NORMAL;")
        _db.executescript(_DB_SCHEMA)
        _migrate_if_needed()
        _db.commit()


def _migrate_if_needed() -> None:
    """Add new columns to tables created before the current schema."""
    # users.whitelisted, users.entry_tag
    cur = _db.execute("PRAGMA table_info(users)")
    cols = {row["name"] for row in cur.fetchall()}
    if "whitelisted" not in cols:
        _db.execute("ALTER TABLE users ADD COLUMN whitelisted INTEGER NOT NULL DEFAULT 0")
    if "entry_tag" not in cols:
        _db.execute("ALTER TABLE users ADD COLUMN entry_tag TEXT")

    # slots.was_replied + slots.last_message
    cur = _db.execute("PRAGMA table_info(slots)")
    cols = {row["name"] for row in cur.fetchall()}
    if "was_replied" not in cols:
        _db.execute("ALTER TABLE slots ADD COLUMN was_replied INTEGER NOT NULL DEFAULT 0")
    if "last_message" not in cols:
        _db.execute("ALTER TABLE slots ADD COLUMN last_message TEXT")

    # retry_queue.is_sos — SOS fast-retry для срочных сообщений
    cur = _db.execute("PRAGMA table_info(retry_queue)")
    cols = {row["name"] for row in cur.fetchall()}
    if "is_sos" not in cols:
        _db.execute("ALTER TABLE retry_queue ADD COLUMN is_sos INTEGER NOT NULL DEFAULT 0")


# ---------- users ----------
def user_upsert(tg_user_id: int, tg_username: Optional[str], first_name: Optional[str]) -> None:
    now = _now()
    with _db_lock:
        cur = _db.execute("SELECT 1 FROM users WHERE tg_user_id = ?", (tg_user_id,))
        if cur.fetchone() is None:
            _db.execute(
                "INSERT INTO users (tg_user_id, tg_username, first_name, banned, first_seen, last_seen) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (tg_user_id, tg_username, first_name, now, now),
            )
        else:
            _db.execute(
                "UPDATE users SET tg_username = COALESCE(?, tg_username), "
                "first_name = COALESCE(?, first_name), last_seen = ? WHERE tg_user_id = ?",
                (tg_username, first_name, now, tg_user_id),
            )
        _db.commit()


def user_is_banned(tg_user_id: int) -> bool:
    with _db_lock:
        cur = _db.execute("SELECT banned FROM users WHERE tg_user_id = ?", (tg_user_id,))
        row = cur.fetchone()
    return bool(row["banned"]) if row else False


def user_set_banned(tg_user_id: int, banned: bool) -> None:
    with _db_lock:
        _db.execute("UPDATE users SET banned = ? WHERE tg_user_id = ?", (1 if banned else 0, tg_user_id))
        _db.commit()


def user_display(tg_user_id: int) -> str:
    with _db_lock:
        cur = _db.execute("SELECT tg_username, first_name FROM users WHERE tg_user_id = ?", (tg_user_id,))
        row = cur.fetchone()
    if not row:
        return str(tg_user_id)
    return row["tg_username"] or row["first_name"] or str(tg_user_id)


def user_list_banned() -> list[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT tg_user_id, tg_username, first_name FROM users "
            "WHERE banned = 1 ORDER BY last_seen DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def user_set_whitelisted(tg_user_id: int, allowed: bool) -> None:
    with _db_lock:
        _db.execute(
            "UPDATE users SET whitelisted = ? WHERE tg_user_id = ?",
            (1 if allowed else 0, tg_user_id),
        )
        _db.commit()


def user_is_whitelisted(tg_user_id: int) -> bool:
    with _db_lock:
        cur = _db.execute(
            "SELECT whitelisted FROM users WHERE tg_user_id = ?", (tg_user_id,)
        )
        row = cur.fetchone()
    return bool(row["whitelisted"]) if row else False


def user_list_whitelisted() -> list[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT tg_user_id, tg_username, first_name FROM users "
            "WHERE whitelisted = 1 ORDER BY last_seen DESC"
        )
        return [dict(row) for row in cur.fetchall()]


def user_list_all() -> list[dict]:
    """All users known to the bot, with their flags. For UI."""
    with _db_lock:
        cur = _db.execute(
            "SELECT u.tg_user_id, u.tg_username, u.first_name, u.banned, u.whitelisted, "
            "u.first_seen, u.last_seen, "
            "EXISTS(SELECT 1 FROM favorites f WHERE f.tg_user_id = u.tg_user_id) AS is_fav "
            "FROM users u ORDER BY u.last_seen DESC"
        )
        return [dict(row) for row in cur.fetchall()]


# ---------- slots ----------
def slot_allocate_or_reuse(tg_user_id: int) -> tuple[int, bool]:
    """Return (slot_n, reused). Sticky: if the user still has an active slot,
    refresh its TTL and reuse the same N; only when they have no slot do we
    pick a new lowest-free N.
    """
    now = _now()
    with _db_lock:
        # Existing non-expired slot?
        cur = _db.execute(
            "SELECT slot_n, was_replied FROM slots "
            "WHERE tg_user_id = ? AND expires_at >= ? "
            "ORDER BY expires_at DESC LIMIT 1",
            (tg_user_id, now),
        )
        row = cur.fetchone()
        if row is not None:
            ttl_h = SLOT_STICKY_HOURS if row["was_replied"] else SLOT_TTL_HOURS
            _db.execute(
                "UPDATE slots SET expires_at = ? WHERE slot_n = ?",
                (now + ttl_h * 3600, row["slot_n"]),
            )
            _db.commit()
            return int(row["slot_n"]), True

        # New slot — lowest free integer >= 1.
        cur = _db.execute("SELECT slot_n FROM slots ORDER BY slot_n")
        taken = {r["slot_n"] for r in cur.fetchall()}
        n = 1
        while n in taken:
            n += 1
        _db.execute(
            "INSERT INTO slots (slot_n, tg_user_id, created_at, expires_at, was_replied) "
            "VALUES (?, ?, ?, ?, 0)",
            (n, tg_user_id, now, now + SLOT_TTL_HOURS * 3600),
        )
        _db.commit()
        return n, False


# Back-compat shim — old tests / admin paths still call slot_allocate.
def slot_allocate(tg_user_id: int) -> int:
    n, _ = slot_allocate_or_reuse(tg_user_id)
    return n


def slot_lookup(n: int) -> Optional[int]:
    """Return tg_user_id of the slot, or None if missing or expired."""
    with _db_lock:
        cur = _db.execute(
            "SELECT tg_user_id, expires_at FROM slots WHERE slot_n = ?", (n,)
        )
        row = cur.fetchone()
    if not row:
        return None
    if row["expires_at"] < _now():
        return None
    return row["tg_user_id"]


def slot_set_last_message(n: int, text: str) -> None:
    """Store the most recent user message text on a slot (for UI display)."""
    with _db_lock:
        _db.execute(
            "UPDATE slots SET last_message = ? WHERE slot_n = ?",
            (text[:200], n),  # cap length so UI stays predictable
        )
        _db.commit()


def slot_mark_replied(n: int) -> None:
    """Mark slot as replied and extend TTL to sticky window (TASK-4)."""
    now = _now()
    with _db_lock:
        _db.execute(
            "UPDATE slots SET was_replied = 1, expires_at = ? WHERE slot_n = ?",
            (now + SLOT_STICKY_HOURS * 3600, n),
        )
        _db.commit()


def slot_free(n: int) -> None:
    with _db_lock:
        _db.execute("DELETE FROM slots WHERE slot_n = ?", (n,))
        _db.commit()


def slot_free_all_for_user(tg_user_id: int) -> None:
    with _db_lock:
        _db.execute("DELETE FROM slots WHERE tg_user_id = ?", (tg_user_id,))
        _db.commit()


def slot_expire_old() -> list[int]:
    """Delete expired slots. Returns list of slot_n freed."""
    now = _now()
    with _db_lock:
        cur = _db.execute("SELECT slot_n FROM slots WHERE expires_at < ?", (now,))
        freed = [row["slot_n"] for row in cur.fetchall()]
        if freed:
            _db.execute("DELETE FROM slots WHERE expires_at < ?", (now,))
            _db.commit()
    return freed


def slot_list_active() -> list[dict]:
    now = _now()
    with _db_lock:
        cur = _db.execute(
            "SELECT s.slot_n, s.tg_user_id, s.created_at, s.expires_at, "
            "s.was_replied, s.last_message, "
            "u.tg_username, u.first_name, u.entry_tag "
            "FROM slots s LEFT JOIN users u USING (tg_user_id) "
            "WHERE s.expires_at >= ? ORDER BY s.slot_n",
            (now,),
        )
        return [dict(row) for row in cur.fetchall()]


# ---------- entry_tag (deeplink category) ----------
def user_set_entry_tag(tg_user_id: int, tag: Optional[str]) -> None:
    with _db_lock:
        _db.execute(
            "UPDATE users SET entry_tag = ? WHERE tg_user_id = ?",
            (tag, tg_user_id),
        )
        _db.commit()


def user_get_entry_tag(tg_user_id: int) -> Optional[str]:
    with _db_lock:
        cur = _db.execute(
            "SELECT entry_tag FROM users WHERE tg_user_id = ?",
            (tg_user_id,),
        )
        row = cur.fetchone()
    return row["entry_tag"] if row else None


# ---------- categories (TASK-1: deeplink referrals) ----------
def cat_add(name: str, tag: str) -> bool:
    """Return True if newly added, False if tag already exists."""
    tag = tag.strip().lower()
    with _db_lock:
        cur = _db.execute("SELECT 1 FROM categories WHERE tag = ?", (tag,))
        if cur.fetchone() is not None:
            return False
        _db.execute(
            "INSERT INTO categories (name, tag, created_at) VALUES (?, ?, ?)",
            (name.strip(), tag, _now()),
        )
        _db.commit()
        return True


def cat_remove(tag: str) -> bool:
    with _db_lock:
        cur = _db.execute("DELETE FROM categories WHERE tag = ?", (tag.strip().lower(),))
        _db.commit()
        return cur.rowcount > 0


def cat_list() -> list[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT id, name, tag, created_at FROM categories ORDER BY name"
        )
        return [dict(row) for row in cur.fetchall()]


def cat_by_tag(tag: str) -> Optional[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT id, name, tag FROM categories WHERE tag = ?",
            (tag.strip().lower(),),
        )
        row = cur.fetchone()
    return dict(row) if row else None


# ---------- retry_queue (TASK-2: delivery retries) ----------
def retry_enqueue(tg_user_id: int, tg_chat_id: int, status_msg_id: int,
                  slot_n: int, payload: str, deadline: int,
                  initial_delay_s: int, *, is_sos: bool = False) -> int:
    """Положить сообщение в retry-очередь.

    `is_sos=True` → fast-retry с шагами 5/15/30/60/120 секунд (вместо
    стандартных 2-15 минут). Используется для срочных сообщений
    (текст содержит «#SOS», «срочно», «urgent» и т.п.).
    """
    with _db_lock:
        cur = _db.execute(
            "INSERT INTO retry_queue "
            "(tg_user_id, tg_chat_id, status_msg_id, slot_n, payload, "
            " attempts, next_try_at, deadline, is_sos) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)",
            (tg_user_id, tg_chat_id, status_msg_id, slot_n, payload,
             _now() + initial_delay_s, deadline, 1 if is_sos else 0),
        )
        _db.commit()
        return int(cur.lastrowid)


def retry_get(retry_id: int) -> Optional[dict]:
    with _db_lock:
        cur = _db.execute("SELECT * FROM retry_queue WHERE id = ?", (retry_id,))
        row = cur.fetchone()
    return dict(row) if row else None


def retry_due() -> list[dict]:
    """All rows ready for another attempt and still within deadline."""
    now = _now()
    with _db_lock:
        cur = _db.execute(
            "SELECT * FROM retry_queue WHERE next_try_at <= ? AND deadline >= ? "
            "ORDER BY next_try_at",
            (now, now),
        )
        return [dict(row) for row in cur.fetchall()]


def retry_expired() -> list[dict]:
    """Rows past deadline — give up."""
    now = _now()
    with _db_lock:
        cur = _db.execute("SELECT * FROM retry_queue WHERE deadline < ?", (now,))
        return [dict(row) for row in cur.fetchall()]


def retry_reschedule(retry_id: int, next_try_at: int) -> None:
    with _db_lock:
        _db.execute(
            "UPDATE retry_queue SET attempts = attempts + 1, next_try_at = ? "
            "WHERE id = ?",
            (next_try_at, retry_id),
        )
        _db.commit()


def retry_delete(retry_id: int) -> None:
    with _db_lock:
        _db.execute("DELETE FROM retry_queue WHERE id = ?", (retry_id,))
        _db.commit()


def retry_delete_for_slot(slot_n: int) -> None:
    with _db_lock:
        _db.execute("DELETE FROM retry_queue WHERE slot_n = ?", (slot_n,))
        _db.commit()


# ---------- AI conversations (TASK: AI helper) ----------
def ai_alloc_slot() -> int:
    """Выделить новый @aiN — наименьший свободный integer >= 1."""
    n = _now()
    with _db_lock:
        cur = _db.execute("SELECT slot_n_ai FROM ai_conversations ORDER BY slot_n_ai")
        taken = {r["slot_n_ai"] for r in cur.fetchall()}
        slot = 1
        while slot in taken:
            slot += 1
        _db.execute(
            "INSERT INTO ai_conversations (slot_n_ai, created_at, last_used_at) "
            "VALUES (?, ?, ?)",
            (slot, n, n),
        )
        _db.commit()
    return slot


def ai_touch_slot(slot_n_ai: int) -> bool:
    """Обновить last_used_at. Returns True если slot существует."""
    n = _now()
    with _db_lock:
        cur = _db.execute(
            "UPDATE ai_conversations SET last_used_at = ? WHERE slot_n_ai = ?",
            (n, slot_n_ai),
        )
        _db.commit()
        return cur.rowcount > 0


def ai_save_message(slot_n_ai: int, role: str, content: str) -> None:
    """Записать одно сообщение в историю чата. role: 'user' | 'assistant'."""
    with _db_lock:
        _db.execute(
            "INSERT INTO ai_messages (slot_n_ai, role, content, ts) "
            "VALUES (?, ?, ?, ?)",
            (slot_n_ai, role, content, _now()),
        )
        _db.commit()


def ai_get_history(slot_n_ai: int, max_messages: int) -> list[dict]:
    """Вернуть последние N сообщений в OpenAI-формате (без system).
    Сортировка по ts asc — старые сначала, чтобы LLM видел хронологию.
    Тай-брейк по id (autoincrement) — критично, потому что несколько
    save_message в одну секунду имеют одинаковый ts, и без id порядок
    неопределён → LLM получает перемешанные роли.
    """
    with _db_lock:
        cur = _db.execute(
            "SELECT role, content FROM ai_messages "
            "WHERE slot_n_ai = ? ORDER BY ts DESC, id DESC LIMIT ?",
            (slot_n_ai, max_messages),
        )
        rows = cur.fetchall()
    # Развернём обратно: сначала старые, потом новые
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def ai_expire_old(ttl_hours: int) -> list[int]:
    """Удалить чаты с last_used_at старше ttl_hours. Возвращает list of slot_n_ai."""
    cutoff = _now() - ttl_hours * 3600
    with _db_lock:
        cur = _db.execute(
            "SELECT slot_n_ai FROM ai_conversations WHERE last_used_at < ?",
            (cutoff,),
        )
        freed = [r["slot_n_ai"] for r in cur.fetchall()]
        if freed:
            placeholders = ",".join("?" * len(freed))
            _db.execute(
                f"DELETE FROM ai_messages WHERE slot_n_ai IN ({placeholders})",
                freed,
            )
            _db.execute(
                f"DELETE FROM ai_conversations WHERE slot_n_ai IN ({placeholders})",
                freed,
            )
            _db.commit()
    return freed


def ai_slot_exists(slot_n_ai: int) -> bool:
    with _db_lock:
        cur = _db.execute(
            "SELECT 1 FROM ai_conversations WHERE slot_n_ai = ?",
            (slot_n_ai,),
        )
        return cur.fetchone() is not None


# ---------- favorites (BETA) ----------
def fav_add(tg_user_id: int, note: Optional[str] = None) -> bool:
    """Returns True if newly added, False if already present."""
    with _db_lock:
        cur = _db.execute("SELECT 1 FROM favorites WHERE tg_user_id = ?", (tg_user_id,))
        if cur.fetchone() is not None:
            if note is not None:
                _db.execute("UPDATE favorites SET note = ? WHERE tg_user_id = ?",
                            (note, tg_user_id))
                _db.commit()
            return False
        _db.execute(
            "INSERT INTO favorites (tg_user_id, added_at, note) VALUES (?, ?, ?)",
            (tg_user_id, _now(), note),
        )
        _db.commit()
        return True


def fav_remove(tg_user_id: int) -> bool:
    with _db_lock:
        cur = _db.execute("DELETE FROM favorites WHERE tg_user_id = ?", (tg_user_id,))
        _db.commit()
        return cur.rowcount > 0


def fav_check(tg_user_id: int) -> bool:
    with _db_lock:
        cur = _db.execute("SELECT 1 FROM favorites WHERE tg_user_id = ?", (tg_user_id,))
        return cur.fetchone() is not None


def fav_list() -> list[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT f.tg_user_id, f.added_at, f.note, u.tg_username, u.first_name "
            "FROM favorites f LEFT JOIN users u USING (tg_user_id) "
            "ORDER BY f.added_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]


# ---------- GPS position (BETA) ----------
def gps_save(lat: float, lon: float, alt: Optional[float], fix_time: Optional[int]) -> None:
    """Upsert the singleton position row for the pocket node."""
    with _db_lock:
        _db.execute(
            "INSERT INTO gps_position (id, lat, lon, alt, fix_time, received_at) "
            "VALUES (1, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "lat=excluded.lat, lon=excluded.lon, alt=excluded.alt, "
            "fix_time=excluded.fix_time, received_at=excluded.received_at",
            (lat, lon, alt, fix_time, _now()),
        )
        _db.commit()


def gps_get_latest() -> Optional[dict]:
    with _db_lock:
        cur = _db.execute(
            "SELECT lat, lon, alt, fix_time, received_at FROM gps_position WHERE id = 1"
        )
        row = cur.fetchone()
    return dict(row) if row else None


def gps_age_minutes() -> Optional[int]:
    """Minutes since the last GPS data point. Prefers fix_time, falls back to received_at."""
    pos = gps_get_latest()
    if not pos:
        return None
    ts = pos.get("fix_time") or pos.get("received_at")
    if not ts:
        return None
    return max(0, int((_now() - ts) / 60))


# ---------- /where rate limit (in-memory) ----------
def where_can_request(tg_user_id: int) -> tuple[bool, int]:
    """Returns (allowed, seconds_to_wait_if_blocked)."""
    if tg_user_id == OWNER_ID:
        return True, 0
    last = _where_last_call.get(tg_user_id)
    now = time.time()
    if last is None:
        return True, 0
    elapsed = now - last
    cooldown = WHERE_RATE_LIMIT_MIN * 60
    if elapsed >= cooldown:
        return True, 0
    return False, int(cooldown - elapsed) + 1


def where_mark_call(tg_user_id: int) -> None:
    _where_last_call[tg_user_id] = time.time()


# ============================================================
# Mesh side
# ============================================================
def _connect_mesh() -> meshtastic.serial_interface.SerialInterface:
    log.info("Connecting to local Meshtastic node over USB...")
    iface = meshtastic.serial_interface.SerialInterface(devPath=MESHTASTIC_PORT)
    pub.subscribe(on_mesh_receive, "meshtastic.receive")

    global _my_node_num, _my_node_id
    # myInfo may take a moment to populate after connection.
    for _ in range(50):
        my_info = getattr(iface, "myInfo", None)
        if my_info is not None and getattr(my_info, "my_node_num", None):
            _my_node_num = my_info.my_node_num
            _my_node_id = f"!{_my_node_num:08x}"
            break
        time.sleep(0.1)

    log.info("Mesh connected. HOME=%s, POCKET=%s", _my_node_id or "?", POCKET_NODE_ID)
    return iface


def on_mesh_receive(packet, interface) -> None:
    """Meshtastic bg-thread callback. Keep it fast and non-blocking."""
    try:
        global _pocket_last_heard

        decoded = packet.get("decoded") or {}
        from_id = packet.get("fromId")
        portnum = decoded.get("portnum")

        # Any packet from pocket counts as a freshness signal.
        if from_id == POCKET_NODE_ID:
            _pocket_last_heard = time.time()

        # GPS position from the pocket node (BETA).
        if portnum == "POSITION_APP" and from_id == POCKET_NODE_ID:
            try:
                pos = decoded.get("position") or {}
                lat = pos.get("latitude")
                lon = pos.get("longitude")
                # Older firmware exposes only the integer-scaled fields.
                if lat is None and pos.get("latitudeI") is not None:
                    lat = pos["latitudeI"] / 1e7
                if lon is None and pos.get("longitudeI") is not None:
                    lon = pos["longitudeI"] / 1e7
                if lat is not None and lon is not None:
                    alt = pos.get("altitude")
                    fix_time = pos.get("time")
                    gps_save(float(lat), float(lon),
                             float(alt) if alt is not None else None,
                             int(fix_time) if fix_time else None)
                    log.info("GPS from pocket: %.6f, %.6f", lat, lon)
            except Exception:
                log.exception("Failed to parse POSITION_APP")
            return

        if portnum != "TEXT_MESSAGE_APP":
            return  # telemetry, routing, etc. — ignore

        # Drop our own text echoes if they ever loop back.
        if _my_node_num and packet.get("from") == _my_node_num:
            return

        text = (decoded.get("text") or "").strip()
        if not text:
            return

        _mesh_queue.put({
            "kind": "mesh_rx",
            "from_id": from_id or "?",
            "text": text,
            "snr": packet.get("rxSnr"),
            "rssi": packet.get("rxRssi"),
        })
        log.info("Mesh RX from %s: %s", from_id, text)
    except Exception:
        log.exception("Error in on_mesh_receive")


# Lock на исходящие LoRa-вызовы. Радио всё равно физически передаёт только
# один пакет в моменте — лок просто матчит реальность и убирает любые гонки
# на _mesh_iface (USB-write) при конкурентных вызовах из разных asyncio-
# обработчиков и retry_worker'а. threading.Lock работает и для sync-, и
# для async-callers (последние используют send_dm_to_pocket_async, который
# гоняет sendText через asyncio.to_thread).
_mesh_send_lock = threading.Lock()


def send_dm_to_pocket(text: str, on_ack=None) -> None:
    """Send a DM to the pocket node. If `on_ack` is given, it will be called
    once when the routing-ACK / NAK arrives (or library timeout fires).
    The callback runs on the meshtastic background thread — keep it light
    (push to _mesh_queue, do real work in the asyncio dispatcher).

    Synchronous: USB-write блокирует поток на 50–200 мс. Из async-кода
    использовать `send_dm_to_pocket_async` — там это вынесено в thread-pool.

    `MESH_DELIVERY_MODE`: при `"fast"` идёт fire-and-forget (wantAck=False,
    on_ack игнорируется). При `"reliable"` (default) — стандартный wantAck.
    """
    if _mesh_iface is None:
        raise RuntimeError("Mesh interface not connected")
    with _mesh_send_lock:
        if MESH_WANT_ACK:
            _mesh_iface.sendText(
                text,
                destinationId=POCKET_NODE_ID,
                wantAck=True,
                onResponse=on_ack,
                hopLimit=MESH_HOP_LIMIT,
            )
        else:
            # Fast mode: fire-and-forget. Никаких ACK / retry / статусов
            # доставки. Подходит для срочных коротких пакетов когда «лишь бы
            # быстрее, а не наверняка».
            _mesh_iface.sendText(
                text,
                destinationId=POCKET_NODE_ID,
                wantAck=False,
                hopLimit=MESH_HOP_LIMIT,
            )


async def send_dm_to_pocket_async(text: str, on_ack=None) -> None:
    """Async-friendly обёртка над send_dm_to_pocket. USB-write уносится в
    thread-pool, asyncio event loop не блокируется на время передачи.
    Сериализация конкурентных вызовов гарантируется внутренним
    `_mesh_send_lock` (один пакет в моменте — как и физическое радио)."""
    await asyncio.to_thread(send_dm_to_pocket, text, on_ack)


def list_nodes_except_self() -> list[dict]:
    if _mesh_iface is None:
        return []
    out: list[dict] = []
    nodes = getattr(_mesh_iface, "nodes", None) or {}
    for nid, node in nodes.items():
        if not isinstance(node, dict):
            continue
        if nid == _my_node_id or node.get("num") == _my_node_num:
            continue
        user = node.get("user") or {}
        out.append({
            "id": nid,
            "name": user.get("longName") or user.get("shortName") or nid,
            "snr": node.get("snr"),
            "last_heard": node.get("lastHeard"),
        })
    return out


def pocket_freshness_hint() -> str:
    """User-facing staleness hint. Empty string = no hint."""
    last = _pocket_last_heard
    if last is None and _mesh_iface is not None:
        nodes = getattr(_mesh_iface, "nodes", None) or {}
        node = nodes.get(POCKET_NODE_ID)
        if isinstance(node, dict):
            lh = node.get("lastHeard")
            if lh:
                last = float(lh)
    if last is None:
        return ""
    age_min = int((time.time() - last) / 60)
    if age_min < POCKET_FRESH_MIN:
        return ""
    if age_min < POCKET_STALE_MIN:
        return f" Последний контакт с {DISPLAY_NAME} — {age_min} мин назад."
    hours = max(1, age_min // 60)
    return (
        f" Похоже, {DISPLAY_NAME} сейчас вне связи — сообщение дойдёт, "
        f"как только связь появится. (Последний контакт ~{hours} ч назад.)"
    )


# ============================================================
# Mesh text parser (what Mikhail types on his pocket node)
# ============================================================
_RE_SOS            = re.compile(r"^#SOS\b\s*(.*)$", re.IGNORECASE | re.DOTALL)
_RE_STANDALONE_CMD = re.compile(r"^!(\w+)(?:\s+(.*))?$", re.DOTALL)
_RE_SLOT_PREFIX    = re.compile(r"^@(\d+)\s*(.*)$", re.DOTALL)
# AI helper: «@ai <вопрос>» — новый чат; «@aiN <вопрос>» — продолжение N-го.
_RE_AI_NEW         = re.compile(r"^@ai\s+(.+)$", re.IGNORECASE | re.DOTALL)
_RE_AI_FOLLOWUP    = re.compile(r"^@ai(\d+)\s+(.+)$", re.IGNORECASE | re.DOTALL)


def parse_mesh_text(text: str) -> dict:
    """Categorise a mesh text message received from Mikhail.

    Returns one of:
      {"kind": "sos",            "text": str}
      {"kind": "ai_followup",    "n": int, "text": str}     # @ai1 текст
      {"kind": "ai_new",         "text": str}               # @ai текст
      {"kind": "standalone_cmd", "cmd": str, "args": str}
      {"kind": "slot_cmd",       "n": int, "cmd": str, "args": str}
      {"kind": "slot_reply",     "n": int, "text": str}
      {"kind": "raw",            "text": str}
    """
    m = _RE_SOS.match(text)
    if m:
        return {"kind": "sos", "text": m.group(1).strip()}

    # AI followup `@aiN` ДО общего @N (тот матчил бы «ai1» как N=ai1 и падал).
    m = _RE_AI_FOLLOWUP.match(text)
    if m:
        return {"kind": "ai_followup", "n": int(m.group(1)),
                "text": m.group(2).strip()}

    m = _RE_AI_NEW.match(text)
    if m:
        return {"kind": "ai_new", "text": m.group(1).strip()}

    m = _RE_STANDALONE_CMD.match(text)
    if m:
        return {"kind": "standalone_cmd", "cmd": m.group(1).lower(), "args": (m.group(2) or "").strip()}

    m = _RE_SLOT_PREFIX.match(text)
    if m:
        n = int(m.group(1))
        rest = m.group(2).strip()
        cm = _RE_STANDALONE_CMD.match(rest)
        if cm:
            return {"kind": "slot_cmd", "n": n, "cmd": cm.group(1).lower(), "args": (cm.group(2) or "").strip()}
        return {"kind": "slot_reply", "n": n, "text": rest}

    return {"kind": "raw", "text": text}


# ============================================================
# Mesh event dispatcher (runs in asyncio loop)
# ============================================================
async def _notify_owner(app: Application, text: str) -> None:
    try:
        await app.bot.send_message(chat_id=OWNER_ID, text=text)
    except Exception:
        log.exception("Failed to notify owner")


async def _dm_user(app: Application, tg_user_id: int, text: str) -> bool:
    try:
        await app.bot.send_message(chat_id=tg_user_id, text=text)
        return True
    except Exception:
        log.exception("Failed to DM TG user %s", tg_user_id)
        return False


def _slot_was_replied(slot_n: int) -> bool:
    """Sync DB query — used by ACK handler to skip redundant receipts after
    Mikhail has already replied to this slot."""
    if slot_n is None:
        return False
    with _db_lock:
        cur = _db.execute("SELECT was_replied FROM slots WHERE slot_n = ?",
                          (slot_n,))
        row = cur.fetchone()
    return bool(row["was_replied"]) if row else False


async def _handle_ack_event(app: Application, evt: dict) -> None:
    """Got a routing-ACK / NAK from the pocket. Tell the original user."""
    chat_id = evt.get("chat_id")
    if not chat_id:
        return
    delivered = bool(evt.get("delivered"))

    # If Mikhail already replied for this slot, the reply itself proved
    # delivery — don't spam the user with an extra "received" tick.
    if delivered and _slot_was_replied(evt.get("slot_n")):
        return

    if delivered:
        # Confirmation that the recipient's pocket node received the LoRa
        # packet — not yet that they "read" it. The reply itself is the
        # read signal, no extra prose needed.
        text = f"✓ Доставлено: {DISPLAY_NAME}."
    else:
        err = evt.get("error") or "таймаут"
        text = (
            f"⚠️ Сообщение не дошло (причина: {err}). "
            "Если это срочно, попробуй ещё раз через минуту."
        )
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        log.exception("ack notify to user %s failed", chat_id)


async def _show_status(update: Update, status_msg, text: str, *,
                       reply_markup=None) -> None:
    """Update the placeholder status message with `text`. If editing is
    refused by Telegram (e.g. message too old / blocked / rate-limited),
    fall back to sending a fresh reply so the user always sees the outcome.
    """
    try:
        await status_msg.edit_text(text, reply_markup=reply_markup)
        return
    except Exception as e:
        log.warning("status edit failed (%s) — falling back to new message", e)
    try:
        await update.message.reply_text(text, reply_markup=reply_markup)
    except Exception:
        log.exception("Fallback status reply also failed")


async def _dm_user_reply(app: Application, tg_user_id: int, text: str) -> bool:
    """Send Mikhail's reply to a public user. We just deliver the text with
    a name prefix so the user knows it's their recipient — the reply is
    itself proof of «read», no explicit "ответил" preamble needed."""
    try:
        await app.bot.send_message(
            chat_id=tg_user_id,
            text=f"{DISPLAY_NAME}: {text}",
            reply_markup=PUBLIC_KEYBOARD,
        )
        return True
    except Exception:
        log.exception("Failed to DM TG user %s with reply", tg_user_id)
        return False


def _reply_status_payload() -> str:
    slots = slot_list_active()
    if not slots:
        return "Слотов нет"
    now = _now()
    parts = []
    for s in slots:
        name = (s.get("tg_username") or s.get("first_name") or str(s["tg_user_id"]))[:8]
        left_h = max(0, (s["expires_at"] - now) // 3600)
        parts.append(f"@{s['slot_n']} {name} {left_h}h")
    msg = " | ".join(parts)
    if len(msg) > MAX_TEXT_LENGTH:
        msg = msg[: MAX_TEXT_LENGTH - 3] + "..."
    return msg


def _reply_gps_payload() -> str:
    """Compact GPS state for !gps from pocket. BETA."""
    if not GPS_ENABLED:
        return "GPS off"
    pos = gps_get_latest()
    if not pos:
        return "GPS: нет фикса"
    age = gps_age_minutes()
    age_s = f"{age}m" if age is not None else "?"
    msg = f"{pos['lat']:.5f},{pos['lon']:.5f} {age_s}"
    if len(msg) > MAX_TEXT_LENGTH:
        msg = msg[: MAX_TEXT_LENGTH - 3] + "..."
    return msg


def _reply_favlist_payload() -> str:
    if not GPS_ENABLED:
        return "GPS off"
    favs = fav_list()
    if not favs:
        return "Избранных нет"
    parts = []
    for f in favs:
        name = (f.get("tg_username") or f.get("first_name") or str(f["tg_user_id"]))[:10]
        parts.append(name)
    msg = "fav: " + ", ".join(parts)
    if len(msg) > MAX_TEXT_LENGTH:
        msg = msg[: MAX_TEXT_LENGTH - 3] + "..."
    return msg


async def _handle_sos(app: Application, sos_text: str) -> None:
    """#SOS triggered from pocket: fan-out to recipients with optional GPS."""
    if not SOS_ENABLED:
        await send_dm_to_pocket_async("SOS off (включи в настройках)")
        await _notify_owner(
            app,
            f"⚠️ #SOS получен, но SOS_ENABLED=False. Сообщение: «{sos_text}»",
        )
        return

    if not SOS_RECIPIENTS:
        await send_dm_to_pocket_async("SOS: список пуст")
        await _notify_owner(
            app,
            "⚠️ #SOS получен, но recipients пуст. Заполни через настройки.",
        )
        return

    # Compose payload.
    body = f"🆘 {SOS_MESSAGE}".strip()
    if sos_text:
        body += f"\n\n*Сообщение от {DISPLAY_NAME}:*\n{sos_text}"

    pos = gps_get_latest()
    age = gps_age_minutes()
    have_loc = (
        SOS_INCLUDE_COORDS
        and pos is not None
        and age is not None
        and age <= GPS_FIX_MAX_MIN
    )
    if have_loc:
        body += (
            f"\n\n📍 Координаты: "
            f"{pos['lat']:.5f}, {pos['lon']:.5f} ({age} мин назад)"
        )
    elif SOS_INCLUDE_COORDS:
        body += "\n\n📍 Координаты сейчас недоступны."

    delivered = 0
    for tg_id in SOS_RECIPIENTS:
        try:
            await app.bot.send_message(chat_id=tg_id, text=body, parse_mode="Markdown")
            if have_loc:
                await app.bot.send_location(
                    chat_id=tg_id,
                    latitude=pos["lat"],
                    longitude=pos["lon"],
                )
            delivered += 1
        except Exception:
            log.exception("SOS to %s failed", tg_id)

    log.warning("SOS triggered. delivered=%d/%d", delivered, len(SOS_RECIPIENTS))
    await send_dm_to_pocket_async(f"SOS отправлен {delivered}/{len(SOS_RECIPIENTS)}")
    await _notify_owner(
        app,
        f"🆘 SOS triggered.\nДоставлено: {delivered}/{len(SOS_RECIPIENTS)}.\n"
        f"Текст: «{sos_text or '—'}»\n"
        f"Координаты: {'да' if have_loc else 'нет'}.",
    )


async def _handle_ai(query: str, *, slot_n_ai: Optional[int]) -> None:
    """AI helper: запрос с pocket-ноды → ответ от LLM обратно в pocket.

    `slot_n_ai=None` → новый диалог (выделим slot). Иначе — продолжение.
    Контекст диалога подтягивается из ai_messages (последние AI_MAX_HISTORY).
    """
    if not AI_ENABLED:
        await send_dm_to_pocket_async(
            "AI off. Включи AI_ENABLED=true в .env (нужен LM Studio локально)."
        )
        return

    query = (query or "").strip()
    if not query:
        await send_dm_to_pocket_async("AI: пустой запрос.")
        return

    # Slot management: новый или существующий
    if slot_n_ai is None:
        slot = ai_alloc_slot()
        history = []
    else:
        if not ai_slot_exists(slot_n_ai):
            await send_dm_to_pocket_async(
                f"@ai{slot_n_ai} не активен. Используй просто «@ai <вопрос>» для нового чата."
            )
            return
        ai_touch_slot(slot_n_ai)
        slot = slot_n_ai
        history = ai_get_history(slot, AI_MAX_HISTORY)

    # Сохраняем user-сообщение СРАЗУ — на случай если LLM упадёт, контекст
    # не потеряется (юзер сможет переспросить, история уже там).
    ai_save_message(slot, "user", query)

    # Строим payload: system + история + новый user-вопрос
    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": query})

    try:
        answer = await ai_helper.chat(
            messages,
            model=AI_MODEL,
            base_url=AI_BASE_URL,
            api_key=AI_API_KEY,
            timeout_sec=AI_TIMEOUT_SEC,
        )
    except Exception as exc:
        log.exception("AI request failed")
        await send_dm_to_pocket_async(
            f"@ai{slot} ошибка: {type(exc).__name__}. Проверь LM Studio."
        )
        return

    # Сохраняем ответ в историю (не системный — system промпт не пишем).
    ai_save_message(slot, "assistant", answer)

    # Шлём обратно в pocket. С префиксом @aiN — в стиле наших обычных слотов.
    # Длинный ответ режется на чанки тем же _chunk_text как в handle_text.
    full = f"@ai{slot} {answer}"
    if len(full) <= MAX_TEXT_LENGTH:
        await send_dm_to_pocket_async(full)
        return
    # Multi-chunk: первый чанк с префиксом и i/N, остальные — продолжение
    chunk_room = max(40, MAX_TEXT_LENGTH - 25)
    parts = _chunk_text(answer, chunk_room)
    for i, part in enumerate(parts):
        prefix = f"@ai{slot} {i + 1}/{len(parts)}"
        out = f"{prefix} {part}"
        try:
            await send_dm_to_pocket_async(out)
            await asyncio.sleep(0.4)
        except Exception:
            log.exception("AI chunk send failed (best-effort, continuing)")


async def _handle_mesh_event(app: Application, evt: dict) -> None:
    kind = evt.get("kind")

    # Routing-ACK / NAK arrived for a sent packet — surface it to the user.
    if kind == "ack":
        await _handle_ack_event(app, evt)
        return

    if kind != "mesh_rx":
        return

    from_id = evt["from_id"]
    text = evt["text"]

    # Anything not from pocket is just mirrored to the owner as a log.
    if from_id != POCKET_NODE_ID:
        await _notify_owner(
            app,
            f"📡 Нода {from_id}:\n{text}\nSNR: {evt.get('snr')} / RSSI: {evt.get('rssi')}",
        )
        return

    parsed = parse_mesh_text(text)
    kind = parsed["kind"]

    # SOS — panic broadcast.
    if kind == "sos":
        await _handle_sos(app, parsed["text"])
        return

    # AI helper: «@ai <вопрос>» — новый чат / «@aiN <вопрос>» — продолжение.
    if kind == "ai_new":
        await _handle_ai(parsed["text"], slot_n_ai=None)
        return
    if kind == "ai_followup":
        await _handle_ai(parsed["text"], slot_n_ai=int(parsed["n"]))
        return

    if kind == "standalone_cmd":
        cmd = parsed["cmd"]
        if cmd == "status":
            await send_dm_to_pocket_async(_reply_status_payload())
        elif cmd == "help":
            help_msg = "@N текст=ответ. @N !ban=бан. !status. !help."
            if GPS_ENABLED:
                help_msg += " GPS(beta): @N !fav/!unfav, !gps, !favlist."
            if SOS_ENABLED:
                help_msg += " #SOS текст = тревога."
            await send_dm_to_pocket_async(help_msg)
        elif cmd == "gps":
            await send_dm_to_pocket_async(_reply_gps_payload())
        elif cmd == "favlist":
            await send_dm_to_pocket_async(_reply_favlist_payload())
        else:
            await send_dm_to_pocket_async(f"!{cmd}? есть: !status, !help")
        await _notify_owner(app, f"🎒 Команда с кармана: !{cmd}")
        return

    if kind == "slot_cmd":
        n = parsed["n"]
        cmd = parsed["cmd"]
        tg_uid = slot_lookup(n)
        if tg_uid is None:
            await send_dm_to_pocket_async(f"@{n} не активен")
            await _notify_owner(app, f"⚠️ С кармана: @{n} !{cmd} — слот не активен.")
            return
        if cmd == "ban":
            user_set_banned(tg_uid, True)
            slot_free_all_for_user(tg_uid)
            dname = user_display(tg_uid)
            await send_dm_to_pocket_async(f"@{n} {dname[:10]} забанен")
            await _notify_owner(app, f"🚫 Забанен {dname} (tg {tg_uid}) через @{n}.")
        elif cmd == "fav":
            if not GPS_ENABLED:
                await send_dm_to_pocket_async(f"@{n} GPS off")
                return
            added = fav_add(tg_uid, note=f"via @{n}")
            dname = user_display(tg_uid)
            await send_dm_to_pocket_async(
                f"@{n} {dname[:10]} {'+fav' if added else 'уже fav'}"
            )
            await _notify_owner(
                app,
                f"⭐ {'Добавлен' if added else 'Уже был'} в избранные: "
                f"{dname} (tg {tg_uid}) через @{n}.",
            )
        elif cmd == "unfav":
            if not GPS_ENABLED:
                await send_dm_to_pocket_async(f"@{n} GPS off")
                return
            removed = fav_remove(tg_uid)
            dname = user_display(tg_uid)
            await send_dm_to_pocket_async(
                f"@{n} {dname[:10]} {'-fav' if removed else 'не fav'}"
            )
            await _notify_owner(
                app,
                f"☆ {'Удалён' if removed else 'Не был'} из избранных: "
                f"{dname} (tg {tg_uid}) через @{n}.",
            )
        else:
            avail = "!ban"
            if GPS_ENABLED:
                avail += ", !fav, !unfav"
            await send_dm_to_pocket_async(f"@{n} !{cmd}? есть: {avail}")
        return

    if kind == "slot_reply":
        n = parsed["n"]
        reply_text = parsed["text"]
        if not reply_text:
            await send_dm_to_pocket_async(f"@{n} пустой ответ")
            return
        tg_uid = slot_lookup(n)
        if tg_uid is None:
            await _notify_owner(
                app,
                f"⚠️ Ответ на @{n}, но слот не активен.\nТекст: {reply_text}",
            )
            await send_dm_to_pocket_async(f"@{n} уже неактуален")
            return
        ok = await _dm_user_reply(app, tg_uid, reply_text)
        if ok:
            # Sticky behaviour (TASK-4): keep slot alive for 10h more,
            # mark as replied so subsequent user messages reuse it at the
            # shorter sticky TTL.
            slot_mark_replied(n)
            retry_delete_for_slot(n)
            await _notify_owner(app, f"✅ @{n} → {user_display(tg_uid)}: {reply_text}")
        else:
            await send_dm_to_pocket_async(f"@{n} не доставлено")
        return

    # kind == "raw"
    await _notify_owner(app, f"🎒 С кармана (не распознано): {text}")


async def mesh_dispatcher(app: Application) -> None:
    loop = asyncio.get_running_loop()
    while True:
        evt = await loop.run_in_executor(None, _mesh_queue.get)
        try:
            await _handle_mesh_event(app, evt)
        except Exception:
            log.exception("Error in mesh dispatcher")


async def expiry_worker(app: Application) -> None:
    while True:
        try:
            freed = slot_expire_old()
            if freed:
                log.info("Expired slots: %s", freed)
                # Retry rows for now-expired slots are orphaned — clean them.
                for n in freed:
                    retry_delete_for_slot(n)
            # AI conversations: чистим неактивные старше AI_TTL_HOURS
            if AI_ENABLED:
                ai_freed = ai_expire_old(AI_TTL_HOURS)
                if ai_freed:
                    log.info("Expired AI conversations: %s", ai_freed)
        except Exception:
            log.exception("expiry_worker failed")
        await asyncio.sleep(60)


async def _show_status_by_id(app: Application, chat_id: int,
                             message_id: int, text: str) -> None:
    """edit_message_text with fallback to send_message — used by retry_worker."""
    try:
        await app.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
        )
        return
    except Exception as e:
        log.warning("retry-edit failed (%s) — sending fresh message", e)
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        log.exception("Fallback send_message also failed")


async def retry_worker(app: Application) -> None:
    """TASK-2: background retries with exponential backoff, capped."""
    while True:
        try:
            # Give up on anything past its deadline.
            for row in retry_expired():
                await _show_status_by_id(
                    app, row["tg_chat_id"], row["status_msg_id"],
                    f"⌛ Связь с {DISPLAY_NAME} не восстановилась — сообщение не доставлено.",
                )
                retry_delete(row["id"])

            # Try due rows.
            for row in retry_due():
                # Capture for the ack callback (closes over loop-local row).
                chat_id = row["tg_chat_id"]
                slot_n = row["slot_n"]
                def _on_ack(packet, _slot=slot_n, _chat=chat_id):
                    try:
                        decoded = packet.get("decoded") or {}
                        routing = decoded.get("routing") or {}
                        err = routing.get("errorReason") or routing.get("error_reason")
                        delivered = err is None or err == "NONE"
                        _mesh_queue.put({
                            "kind": "ack",
                            "delivered": delivered,
                            "error": err,
                            "slot_n": _slot,
                            "chat_id": _chat,
                        })
                    except Exception:
                        log.exception("retry-ack cb failed")

                try:
                    await send_dm_to_pocket_async(row["payload"], on_ack=_on_ack)
                except Exception:
                    log.info("retry_id=%s still failing (attempt %d, sos=%s)",
                             row["id"], row["attempts"] + 1, row["is_sos"])
                    if row["is_sos"]:
                        # SOS fast-retry: 5 → 15 → 30 → 60 → 120 → 120 ... сек
                        attempt = row["attempts"]
                        if attempt < len(_RETRY_SOS_BACKOFF_SEC):
                            delay = _RETRY_SOS_BACKOFF_SEC[attempt]
                        else:
                            delay = _RETRY_SOS_BACKOFF_SEC[-1]
                    else:
                        base = RETRY_INITIAL_DELAY_MIN * 60
                        delay = min(base * (2 ** row["attempts"]),
                                    RETRY_MAX_INTERVAL_MIN * 60)
                    retry_reschedule(row["id"], _now() + int(delay))
                    continue

                await _show_status_by_id(
                    app, chat_id, row["status_msg_id"],
                    "📨 Сообщение отправлено. Ответ обычно в течение 2–5 минут.",
                )
                retry_delete(row["id"])
                log.info("retry_id=%s delivered", row["id"])
        except Exception:
            log.exception("retry_worker iteration failed")

        # Раньше было 60 — но при SOS fast-retry интервалы 5-15 сек,
        # и проверять due-rows раз в минуту не годится. Один SELECT в БД
        # каждые 5 сек — не нагружает.
        await asyncio.sleep(5)


async def cmd_retry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline button «🔄 Попробовать ещё раз» on a failed-status message."""
    q = update.callback_query
    if q is None or not (q.data or "").startswith("retry:"):
        return
    try:
        retry_id = int((q.data or "").split(":", 1)[1])
    except ValueError:
        await q.answer("Неверная кнопка", show_alert=False)
        return

    row = retry_get(retry_id)
    if row is None:
        # Already processed by worker or deleted.
        await q.answer("Уже доставлено или истекло", show_alert=False)
        try:
            await q.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    await q.answer("Пробую сейчас…")
    chat_id_for_ack = row["tg_chat_id"]
    slot_n_for_ack = row["slot_n"]
    def _on_ack(packet, _slot=slot_n_for_ack, _chat=chat_id_for_ack):
        try:
            decoded = packet.get("decoded") or {}
            routing = decoded.get("routing") or {}
            err = routing.get("errorReason") or routing.get("error_reason")
            delivered = err is None or err == "NONE"
            _mesh_queue.put({
                "kind": "ack",
                "delivered": delivered,
                "error": err,
                "slot_n": _slot,
                "chat_id": _chat,
            })
        except Exception:
            log.exception("manual-retry ack cb failed")

    try:
        await send_dm_to_pocket_async(row["payload"], on_ack=_on_ack)
    except Exception:
        log.exception("manual retry failed for retry_id=%s", retry_id)
        try:
            await q.edit_message_text(
                f"⏳ Пока не получилось. {DISPLAY_NAME} пока вне связи — "
                "попробую ещё автоматически.",
                reply_markup=_retry_inline_markup(retry_id),
            )
        except Exception as e:
            log.warning("retry-edit on manual retry failed: %s", e)
        retry_reschedule(retry_id, _now() + RETRY_INITIAL_DELAY_MIN * 60)
        return

    success = "📨 Сообщение отправлено. Ответ обычно в течение 2–5 минут."
    try:
        await q.edit_message_text(success)
    except Exception as e:
        log.warning("retry-edit on success failed (%s) — sending new msg", e)
        try:
            await context.bot.send_message(chat_id=row["tg_chat_id"], text=success)
        except Exception:
            log.exception("fallback send_message also failed")
    retry_delete(retry_id)


# ============================================================
# Telegram handlers
# ============================================================
GREETING_PUBLIC = (
    f"👋 Привет! Можешь написать сообщение для {DISPLAY_NAME} — я передам.\n\n"
    f"Одно сообщение — до *{MAX_TEXT_LENGTH}* символов.\n"
    "Пиши *ёмко и по делу* — не по кусочкам «привет / как дела / ты где»."
    " Одно толковое сообщение лучше пяти обрывков.\n\n"
    "Ответ придёт сюда же."
)

def _greeting_owner() -> str:
    base = (
        "🛠 *Админ-режим.*\n"
        "Плейн-текст от тебя → DM на карманную ноду (echo-тест).\n"
        "Удобнее настраивать через GUI (run\\_gui.bat) — там есть Настройки, Пользователи и Категории.\n\n"
        "*Команды:*\n"
        "/nodes — видимые ноды (без домашней)\n"
        "/slots — активные слоты @N\n"
        "/dm `!nodeid` текст — DM конкретной ноде\n"
        "/broadcast текст — broadcast всем\n"
        "/ban `<tg_id>` — забанить, /unban `<tg_id>`, /banlist\n"
        "/allow `<tg_id>` — добавить в whitelist, /disallow, /allowed\n"
        "/link — реферальные ссылки по категориям (для копирования)\n"
    )
    wl_state = "ВКЛ (закрытый бот)" if WHITELIST_ENABLED else "выкл (открытый бот)"
    base += f"_Whitelist mode: {wl_state}._\n"
    base += (
        "_Sticky слоты: 20ч до первого ответа, 10ч после. "
        "Повторные сообщения от одного юзера — тот же @N._\n"
        "_Неуспешные доставки ставятся в очередь на авто-ретрай._\n"
    )
    gps_block = (
        "\n*GPS / локация (бета, не тестировалась):*\n"
        "/where — текущая локация\n"
        "/fav `<tg_id>` `[note]` — добавить в избранные (доступ к /where), /unfav, /favlist\n"
        "/gps — отладочная инфа о последнем фиксе\n"
        f"_GPS_ENABLED = {'True' if GPS_ENABLED else 'False'}._\n"
    )
    sos_block = (
        "\n*SOS (тревога):*\n"
        f"_SOS_ENABLED = {'True' if SOS_ENABLED else 'False'}, "
        f"recipients: {len(SOS_RECIPIENTS)}._\n"
        "Триггер: с карманной ноды напиши `#SOS текст`. "
        "Бот разошлёт всем из списка SOS-получателей "
        f"({'с координатами' if SOS_INCLUDE_COORDS else 'без координат'} — настраивается)."
    )
    mesh_line = "\n\n*С ноды:* `@N текст` — ответ, `@N !ban` — бан, `!status`, `!help`"
    if GPS_ENABLED:
        mesh_line += ", `@N !fav`, `@N !unfav`, `!gps`, `!favlist`"
    if SOS_ENABLED:
        mesh_line += ", `#SOS текст` — тревога"
    mesh_line += "."
    return base + gps_block + sos_block + mesh_line


GREETING_OWNER = _greeting_owner()


def _sender_tag(user) -> str:
    if user is None:
        return "?"
    raw = user.username or user.first_name or str(user.id)
    return raw[:MAX_USERNAME_IN_PREFIX]


def _format_lora_packet(slot_n: int, user, text: str, entry_tag: Optional[str] = None,
                        chunk_idx: int = 0, chunks_total: int = 1) -> str:
    """Mikhail-facing packet format.

    Без tag, один пакет:    "[@3 vasya 16:15] text"
    С tag:                  "[@3 work:vasya 16:15] text"
    Multi-chunk (1/N):      "[@3 vasya 16:15 1/3] beginning..."
    Multi-chunk (2/N):      "[@3 vasya 16:15 2/3] continuation..."
    """
    ts = datetime.now().strftime("%H:%M")
    sender = _sender_tag(user)
    if entry_tag:
        sender = f"{entry_tag[:6]}:{sender}"
    if chunks_total > 1:
        return f"[@{slot_n} {sender} {ts} {chunk_idx + 1}/{chunks_total}] {text}"
    return f"[@{slot_n} {sender} {ts}] {text}"


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """Разбивает длинный текст на части по `max_chars`. Стараемся резать
    по пробелу — слова не рубятся пополам если возможно. Минимум 1 чанк.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        # Пытаемся резать по последнему пробелу в окне max_chars
        window = remaining[:max_chars]
        cut = window.rfind(" ")
        if cut < max_chars // 2:  # пробел слишком близко к началу — режем по символам
            cut = max_chars
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return chunks


# ----- Reply keyboard for public users (TASK-8) -----
_KEYBOARD_WHERE = f"📍 Где {DISPLAY_NAME}"
_KEYBOARD_HELP  = "ℹ️ Помощь"

PUBLIC_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton(_KEYBOARD_WHERE), KeyboardButton(_KEYBOARD_HELP)]],
    resize_keyboard=True,
    is_persistent=True,
)


def _retry_inline_markup(retry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Попробовать ещё раз", callback_data=f"retry:{retry_id}")]
    ])


def _owner_only(fn):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if not u or u.id != OWNER_ID:
            return
        return await fn(update, context)
    return wrapper


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if u is None or update.message is None:
        return
    user_upsert(u.id, u.username, u.first_name)

    # Deeplink payload (TASK-1). /start <tag> → set entry_tag if tag known.
    tag_captured: Optional[str] = None
    if context.args:
        candidate = context.args[0].strip().lower()
        cat = cat_by_tag(candidate)
        if cat is not None:
            user_set_entry_tag(u.id, cat["tag"])
            tag_captured = cat["name"]

    if u.id == OWNER_ID:
        await update.message.reply_text(GREETING_OWNER, parse_mode="Markdown")
        return

    greeting = GREETING_PUBLIC
    if tag_captured:
        greeting = (
            f"👋 Привет! Ты здесь из «{tag_captured}» — {DISPLAY_NAME} увидит это в сообщении.\n\n"
            + greeting
        )
    await update.message.reply_text(
        greeting, parse_mode="Markdown", reply_markup=PUBLIC_KEYBOARD,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


@_owner_only
async def cmd_nodes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nodes = list_nodes_except_self()
    if not nodes:
        await update.message.reply_text("Никого не видно.")
        return
    lines = ["Ноды в эфире (без домашней):"]
    for n in nodes:
        snr = n.get("snr") if n.get("snr") is not None else "?"
        mark = " 🎒" if n["id"] == POCKET_NODE_ID else ""
        lines.append(f"• {n['id']} — {n['name']} (SNR: {snr}){mark}")
    await update.message.reply_text("\n".join(lines))


@_owner_only
async def cmd_slots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    slots = slot_list_active()
    if not slots:
        await update.message.reply_text("Слотов нет.")
        return
    now = _now()
    lines = ["Активные слоты:"]
    for s in slots:
        name = s.get("tg_username") or s.get("first_name") or str(s["tg_user_id"])
        left = max(0, s["expires_at"] - now)
        h, rem = divmod(left, 3600)
        m = rem // 60
        lines.append(f"• @{s['slot_n']} {name} — осталось {h}ч {m}м (tg id {s['tg_user_id']})")
    await update.message.reply_text("\n".join(lines))


@_owner_only
async def cmd_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _mesh_iface:
        await update.message.reply_text("Нода не подключена.")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /dm !nodeid текст")
        return
    dest = context.args[0]
    text = " ".join(context.args[1:])
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(f"Слишком длинно ({len(text)}/{MAX_TEXT_LENGTH}).")
        return
    try:
        _mesh_iface.sendText(text, destinationId=dest, wantAck=True)
        await update.message.reply_text(f"✅ DM → {dest}:\n{text}")
    except Exception as e:
        log.exception("DM send failed")
        await update.message.reply_text(f"❌ Ошибка: {e}")


@_owner_only
async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _mesh_iface:
        await update.message.reply_text("Нода не подключена.")
        return
    if not context.args:
        await update.message.reply_text("Использование: /broadcast текст")
        return
    text = " ".join(context.args)
    if len(text) > MAX_TEXT_LENGTH:
        await update.message.reply_text(f"Слишком длинно ({len(text)}/{MAX_TEXT_LENGTH}).")
        return
    try:
        _mesh_iface.sendText(text)
        await update.message.reply_text(f"📡 В эфир:\n{text}")
    except Exception as e:
        log.exception("broadcast failed")
        await update.message.reply_text(f"❌ Ошибка: {e}")


@_owner_only
async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /ban <tg_user_id>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    user_upsert(tg_id, None, None)
    user_set_banned(tg_id, True)
    slot_free_all_for_user(tg_id)
    await update.message.reply_text(f"🚫 Забанен {tg_id} ({user_display(tg_id)}).")


@_owner_only
async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /unban <tg_user_id>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    user_set_banned(tg_id, False)
    await update.message.reply_text(f"✅ Разбанен {tg_id} ({user_display(tg_id)}).")


@_owner_only
async def cmd_banlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = user_list_banned()
    if not rows:
        await update.message.reply_text("Банов нет.")
        return
    lines = ["Забанены:"]
    for r in rows:
        name = r["tg_username"] or r["first_name"] or "?"
        lines.append(f"• {r['tg_user_id']} — {name}")
    await update.message.reply_text("\n".join(lines))


@_owner_only
async def cmd_allow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Whitelist a user (gives access in closed mode)."""
    if not context.args:
        await update.message.reply_text("Использование: /allow <tg_user_id>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    user_upsert(tg_id, None, None)
    user_set_whitelisted(tg_id, True)
    mode = "(закрытый режим)" if WHITELIST_ENABLED else "(открытый режим — пометка на будущее)"
    await update.message.reply_text(
        f"✅ В whitelist: {tg_id} ({user_display(tg_id)}) {mode}."
    )


@_owner_only
async def cmd_disallow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /disallow <tg_user_id>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    user_set_whitelisted(tg_id, False)
    await update.message.reply_text(
        f"☐ Из whitelist: {tg_id} ({user_display(tg_id)})."
    )


@_owner_only
async def cmd_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = user_list_whitelisted()
    mode = "ВКЛ" if WHITELIST_ENABLED else "выкл (открытый бот)"
    if not rows:
        await update.message.reply_text(
            f"Whitelist пуст. Режим whitelist: {mode}."
        )
        return
    lines = [f"Whitelist (режим: {mode}):"]
    for r in rows:
        name = r["tg_username"] or r["first_name"] or "?"
        lines.append(f"• {r['tg_user_id']} — {name}")
    await update.message.reply_text("\n".join(lines))


@_owner_only
async def cmd_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List referral deeplinks for each configured category (TASK-1)."""
    cats = cat_list()
    if not cats:
        await update.message.reply_text(
            "Категорий ещё нет. Добавь в GUI → Настройки → Категории."
        )
        return
    try:
        me = await context.bot.get_me()
        username = me.username
    except Exception:
        username = "your_bot"
    lines = ["*Реферальные ссылки по категориям:*\n"]
    for c in cats:
        url = f"https://t.me/{username}?start={c['tag']}"
        lines.append(f"• *{c['name']}* (`{c['tag']}`)\n  {url}")
    lines.append(
        "\n_Поделись нужной ссылкой — пришедший по ней увидит категорию "
        "в префиксе сообщения у тебя в кармане._"
    )
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True,
    )


# ============================================================
# GPS / location sharing (BETA)
# ============================================================
_LOCATION_UNAVAILABLE = "Локация недоступна."


async def cmd_where(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Public command: only favorites get a real answer.

    Non-favorites and non-GPS_ENABLED states all return the same string,
    so outsiders can not deduce that a privileged command exists.
    """
    u = update.effective_user
    if u is None or update.message is None:
        return

    user_upsert(u.id, u.username, u.first_name)

    is_owner = u.id == OWNER_ID

    # Single uniform "no" path for: feature off, not in favorites, banned.
    if not GPS_ENABLED and not is_owner:
        await update.message.reply_text(_LOCATION_UNAVAILABLE)
        return
    if user_is_banned(u.id):
        await update.message.reply_text(_LOCATION_UNAVAILABLE)
        return
    if not is_owner and not fav_check(u.id):
        await update.message.reply_text(_LOCATION_UNAVAILABLE)
        return

    # Rate limit (skipped for owner).
    allowed, wait_s = where_can_request(u.id)
    if not allowed:
        await update.message.reply_text(
            f"Подожди ещё {wait_s} сек перед следующим запросом."
        )
        return

    pos = gps_get_latest()
    age = gps_age_minutes()
    if not pos or age is None or age > GPS_FIX_MAX_MIN:
        await update.message.reply_text(_LOCATION_UNAVAILABLE)
        return

    where_mark_call(u.id)

    # Send the actual location pin.
    try:
        await context.bot.send_location(
            chat_id=update.effective_chat.id,
            latitude=pos["lat"],
            longitude=pos["lon"],
        )
    except Exception:
        log.exception("send_location failed")
        await update.message.reply_text(_LOCATION_UNAVAILABLE)
        return

    # Caption with freshness/altitude.
    parts = [f"Фикс: {age} мин назад"]
    alt = pos.get("alt")
    if alt is not None:
        parts.append(f"высота {int(alt)} м")
    if age <= GPS_FIX_FRESH_MIN:
        prefix = "📍"
    elif age <= GPS_FIX_STALE_MIN:
        prefix = "📍 (немного устарело)"
    else:
        prefix = "📍 (давно не обновлялось)"
    suffix = "\n_бета: GPS-функция не тестировалась автором_" if is_owner else ""
    await update.message.reply_text(
        f"{prefix} {' · '.join(parts)}.{suffix}",
        parse_mode="Markdown" if suffix else None,
    )


@_owner_only
async def cmd_fav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Использование: /fav <tg_user_id> [заметка]"
        )
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    note = " ".join(context.args[1:]) if len(context.args) > 1 else None
    user_upsert(tg_id, None, None)
    added = fav_add(tg_id, note)
    if not GPS_ENABLED:
        beta = "\n⚠️ GPS_ENABLED = False — функция выключена. /where для них пока не сработает."
    else:
        beta = "\n⚠️ Бета: GPS не тестировался автором, поведение может удивить."
    await update.message.reply_text(
        f"{'⭐ Добавлен' if added else '⚠️ Уже был'} в избранные: "
        f"{tg_id} ({user_display(tg_id)}).{beta}"
    )


@_owner_only
async def cmd_unfav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Использование: /unfav <tg_user_id>")
        return
    try:
        tg_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ожидал numeric tg_user_id.")
        return
    removed = fav_remove(tg_id)
    await update.message.reply_text(
        f"{'☆ Удалён' if removed else '— не был'} из избранных: "
        f"{tg_id} ({user_display(tg_id)})."
    )


@_owner_only
async def cmd_favlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    favs = fav_list()
    if not favs:
        await update.message.reply_text("Избранных нет.")
        return
    lines = ["Избранные (для /where):"]
    for f in favs:
        name = f.get("tg_username") or f.get("first_name") or "?"
        note = f" — {f['note']}" if f.get("note") else ""
        lines.append(f"• {f['tg_user_id']} — {name}{note}")
    if not GPS_ENABLED:
        lines.append("")
        lines.append("⚠️ GPS_ENABLED = False — /where сейчас отвечает «недоступно» всем.")
    await update.message.reply_text("\n".join(lines))


@_owner_only
async def cmd_gps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner debug: show raw GPS state of pocket node."""
    if not GPS_ENABLED:
        await update.message.reply_text(
            "GPS_ENABLED = False. Включи флаг в relay.py, перезапусти.\n"
            "(Бета — функция не тестировалась автором.)"
        )
        return
    pos = gps_get_latest()
    if not pos:
        await update.message.reply_text(
            "GPS-фиксов от карманной ноды ещё не было.\n"
            "Возможные причины: GPS-модуль не подключён / не нашёл небо / "
            "позиции ещё не пришли по мешу."
        )
        return
    age = gps_age_minutes()
    lines = [
        "GPS pocket (beta):",
        f"  lat: {pos['lat']:.6f}",
        f"  lon: {pos['lon']:.6f}",
    ]
    if pos.get("alt") is not None:
        lines.append(f"  alt: {pos['alt']:.1f} м")
    if pos.get("fix_time"):
        lines.append(f"  fix_time: {pos['fix_time']}")
    if pos.get("received_at"):
        lines.append(f"  received_at: {pos['received_at']}")
    if age is not None:
        lines.append(f"  age: {age} мин")
    await update.message.reply_text("\n".join(lines))
    try:
        await context.bot.send_location(
            chat_id=update.effective_chat.id,
            latitude=pos["lat"],
            longitude=pos["lon"],
        )
    except Exception:
        log.exception("debug send_location failed")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if u is None or update.message is None:
        return
    text = (update.message.text or "").strip()
    if not text:
        return

    # Reply-keyboard button synthesis (TASK-8).
    if u.id != OWNER_ID:
        if text == _KEYBOARD_WHERE:
            await cmd_where(update, context)
            return
        if text == _KEYBOARD_HELP:
            await cmd_start(update, context)
            return

    # Owner → admin echo (test path, no slot).
    if u.id == OWNER_ID:
        if not _mesh_iface:
            await update.message.reply_text("Сеть не подключена.")
            return
        payload = f"[admin] {text}"
        if len(payload) > MAX_TEXT_LENGTH:
            await update.message.reply_text(
                f"Слишком длинно ({len(payload)}/{MAX_TEXT_LENGTH})."
            )
            return
        try:
            await send_dm_to_pocket_async(payload)
            await update.message.reply_text(f"🧪 → карман:\n{payload}")
        except Exception as e:
            log.exception("admin echo send failed")
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return

    # Public user path.
    user_upsert(u.id, u.username, u.first_name)

    if user_is_banned(u.id):
        await update.message.reply_text(
            f"{DISPLAY_NAME} сейчас не принимает от тебя сообщения.",
            reply_markup=PUBLIC_KEYBOARD,
        )
        return

    if WHITELIST_ENABLED and not user_is_whitelisted(u.id):
        await update.message.reply_text(
            "Сейчас доступ открыт только для разрешённых собеседников.",
            reply_markup=PUBLIC_KEYBOARD,
        )
        return

    if not _mesh_iface:
        await update.message.reply_text(
            "Сейчас не могу передать сообщение, попробуй чуть позже.",
            reply_markup=PUBLIC_KEYBOARD,
        )
        return

    # Allocate / reuse sticky slot (TASK-4).
    n, reused = slot_allocate_or_reuse(u.id)
    slot_set_last_message(n, text)
    tag = user_get_entry_tag(u.id)
    single_payload = _format_lora_packet(n, u, text, entry_tag=tag)

    # UTF-8 chunking: если итоговый пакет с префиксом больше MAX_TEXT_LENGTH —
    # разбиваем на части `[@N user time 1/3] ... 2/3] ... 3/3]`, отправляем
    # подряд. Сейчас best-effort: если какой-то чанк упал, продолжаем
    # остальные, юзеру говорим что разбито на N частей. Retry-очередь не
    # используется для multi-chunk (она хранит один payload).
    chunked_payloads: list[str] = []
    if len(single_payload) <= MAX_TEXT_LENGTH:
        payload = single_payload
    else:
        # Резерв на «X/Y» в префиксе плюс пробел — ~6 символов сверху обычного
        chunk_room = max(40, MAX_TEXT_LENGTH - 30)
        text_chunks = _chunk_text(text, chunk_room)
        chunked_payloads = [
            _format_lora_packet(
                n, u, ct, entry_tag=tag,
                chunk_idx=i, chunks_total=len(text_chunks),
            )
            for i, ct in enumerate(text_chunks)
        ]
        payload = chunked_payloads[0]   # на retry/ACK кладём первый чанк

    # Параллельно: TG-статус (HTTP к Telegram, ~500–1000 мс) и LoRa-передача
    # (USB+эфир, обычно сравнимо). Раньше это шло последовательно, экономим
    # 0.3–1 с на каждое сообщение. ACK callback ниже захватывает chat_id из
    # closure (а не из status_msg), поэтому даже если status_msg-задача
    # упадёт, "✓ Доставлено" всё равно прилетит юзеру. Race-condition нет.
    #
    # IMPORTANT: НЕ прикреплять ReplyKeyboardMarkup к status_msg —
    # Telegram отказывается edit'ить такие сообщения. Клавиатура уже стикки
    # с /start.
    status_task = asyncio.create_task(
        update.message.reply_text(
            f"📨 Передаю сообщение для {DISPLAY_NAME}…"
        )
    )

    # ACK / delivery-receipt callback — fires from the meshtastic bg thread
    # when the routing-ACK from the pocket node arrives (or library timeout).
    chat_id = update.effective_chat.id
    def _on_ack(packet, _slot=n, _chat=chat_id):
        try:
            decoded = packet.get("decoded") or {}
            routing = decoded.get("routing") or {}
            err = routing.get("errorReason") or routing.get("error_reason")
            delivered = err is None or err == "NONE"
            _mesh_queue.put({
                "kind": "ack",
                "delivered": delivered,
                "error": err,
                "slot_n": _slot,
                "chat_id": _chat,
            })
        except Exception:
            log.exception("ack callback failed")

    send_failed: Optional[Exception] = None
    try:
        await send_dm_to_pocket_async(payload, on_ack=_on_ack)
    except Exception as exc:
        send_failed = exc
        log.exception("Initial send to pocket failed")

    # Multi-chunk: первый чанк ушёл — досылаем остальные подряд (best-effort,
    # без retry / ACK). Между ними небольшая пауза чтобы не перегружать LoRa.
    if send_failed is None and len(chunked_payloads) > 1:
        for extra in chunked_payloads[1:]:
            try:
                await asyncio.sleep(0.4)
                await send_dm_to_pocket_async(extra)
            except Exception:
                log.exception("Multi-chunk follow-up send failed (best-effort, continuing)")

    # Дожидаемся placeholder для последующих edit'ов. Если он упал
    # (TG NetworkError) — деградируем чисто: без placeholder'а, но
    # ack-flow по-прежнему отработает.
    try:
        status_msg = await status_task
    except Exception:
        log.exception("status reply_text failed; continuing without placeholder")
        status_msg = None

    if send_failed is not None:
        if status_msg is not None:
            now = _now()
            deadline = now + (SLOT_STICKY_HOURS if reused else SLOT_TTL_HOURS) * 3600
            # SOS fast-retry: текст содержит #SOS / срочно / urgent →
            # короткие интервалы (5/15/30/60/120 сек) и сразу первая попытка.
            urgent = _is_urgent(text)
            initial_delay = _RETRY_SOS_BACKOFF_SEC[0] if urgent else RETRY_INITIAL_DELAY_MIN * 60
            retry_id = retry_enqueue(
                u.id, update.effective_chat.id, status_msg.message_id,
                n, payload, deadline, initial_delay,
                is_sos=urgent,
            )
            if urgent:
                queue_text = (
                    f"⏳ {DISPLAY_NAME} пока вне связи. Срочное сообщение в "
                    "очереди — повторяю каждые несколько секунд."
                )
            else:
                queue_text = (
                    f"⏳ {DISPLAY_NAME} пока вне связи. Сообщение в очереди — "
                    "попробую автоматически в ближайшие минуты."
                )
            await _show_status(
                update, status_msg, queue_text,
                reply_markup=_retry_inline_markup(retry_id),
            )
        else:
            # Редкий double-fail: TG reply_text упал И mesh send упал.
            # status_msg нет → retry_queue не используем (для retry нужен
            # message_id для будущих edit'ов). Залогируем и пропустим —
            # прошивка сама ретранслирует sendText до 3 раз через wantAck.
            log.warning(
                "Double failure: TG reply_text + mesh send. User=%s, slot=@%s",
                u.id, n,
            )
        return

    # Success branch — fresh vs stale hint for the user.
    hint = pocket_freshness_hint()
    if len(chunked_payloads) > 1:
        success_text = (
            f"📨 Длинное сообщение разбито на {len(chunked_payloads)} частей и "
            "отправлено. Ответ обычно в течение 2–5 минут."
        )
    else:
        success_text = "📨 Сообщение отправлено. Ответ обычно в течение 2–5 минут."
    if hint:
        success_text += "\n" + hint.strip()
    if status_msg is not None:
        await _show_status(update, status_msg, success_text)


async def _reject_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    if u is None or update.message is None:
        return
    if u.id == OWNER_ID:
        await update.message.reply_text("Админ: только текст в echo-режим.")
        return
    await update.message.reply_text(
        f"Умею только текст — до {MAX_TEXT_LENGTH} символов."
    )


# ============================================================
# Post-init / main
# ============================================================
async def on_post_init(app: Application) -> None:
    asyncio.create_task(mesh_dispatcher(app))
    asyncio.create_task(expiry_worker(app))
    asyncio.create_task(retry_worker(app))
    log.info(
        "Relay ready. Owner=%s, Pocket=%s, Home=%s",
        OWNER_ID, POCKET_NODE_ID, _my_node_id,
    )


def _register_handlers(app: Application) -> None:
    """Все handler'ы бота. Вынесено для повторного использования при
    перезапуске polling после NetworkError."""
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("nodes", cmd_nodes))
    app.add_handler(CommandHandler("slots", cmd_slots))
    app.add_handler(CommandHandler("dm", cmd_dm))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("banlist", cmd_banlist))

    app.add_handler(CommandHandler("allow", cmd_allow))
    app.add_handler(CommandHandler("disallow", cmd_disallow))
    app.add_handler(CommandHandler("allowed", cmd_allowed))

    # TASK-1: referral deeplinks
    app.add_handler(CommandHandler("link", cmd_link))

    # TASK-2 + TASK-8: inline retry button
    app.add_handler(CallbackQueryHandler(cmd_retry_cb, pattern=r"^retry:"))

    # GPS / location sharing (BETA). /where stays registered so the
    # owner can self-test even when GPS_ENABLED is False; non-favorites
    # always get the same uniform "недоступно" reply.
    app.add_handler(CommandHandler("where", cmd_where))
    app.add_handler(CommandHandler("fav", cmd_fav))
    app.add_handler(CommandHandler("unfav", cmd_unfav))
    app.add_handler(CommandHandler("favlist", cmd_favlist))
    app.add_handler(CommandHandler("gps", cmd_gps))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    for f in (
        filters.Sticker.ALL, filters.PHOTO, filters.VIDEO, filters.VIDEO_NOTE,
        filters.VOICE, filters.AUDIO, filters.ANIMATION, filters.Document.ALL,
        filters.LOCATION, filters.CONTACT, filters.POLL,
    ):
        app.add_handler(MessageHandler(f, _reject_media))


def _build_app() -> Application:
    """Каждый перезапуск polling требует свежий Application — старый закрыт
    своим event-loop'ом после исключения. Mesh-иntфейс и БД глобальны и
    переживают перезапуск без изменений."""
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_post_init)
        .build()
    )
    _register_handlers(app)
    return app


def _run_polling_with_retry() -> None:
    """Бесконечный цикл: запускаем polling, ловим сетевые/конфликтные ошибки
    Telegram и перезапускаемся с экспоненциальным backoff. Ctrl+C / SIGTERM
    выходят чисто; нормальный return из run_polling (граceful shutdown)
    тоже останавливает цикл."""
    delay = POLLING_RESTART_INITIAL_SEC
    while True:
        run_started_at = time.time()
        try:
            app = _build_app()
            log.info("Starting Telegram polling...")
            # poll_interval=0.3 — пауза между long-poll'ами, чем меньше тем
            # быстрее реакция на входящие. timeout=30 — keep-alive long-poll.
            # Стандартные production-значения PTB.
            app.run_polling(poll_interval=0.3, timeout=30)
            # Граceful shutdown (Application.stop() / SIGTERM из PTB) —
            # не ошибка, выходим из цикла.
            log.info("Polling exited cleanly. Main loop stopping.")
            return
        except KeyboardInterrupt:
            log.info("Ctrl+C — shutting down.")
            return
        except RetryAfter as e:
            # Telegram прямо говорит «подожди столько-то». Уважаем и
            # сбрасываем backoff к initial.
            wait = int(getattr(e, "retry_after", 30)) + 1
            log.warning("Telegram RetryAfter: wait %ds.", wait)
            time.sleep(wait)
            delay = POLLING_RESTART_INITIAL_SEC
            continue
        except (NetworkError, TimedOut) as e:
            log.warning(
                "Telegram network problem: %s — restart in %ds.",
                e, delay,
            )
        except Conflict as e:
            # Другая копия бота с тем же токеном съела getUpdates.
            # Восстанавливать смысла нет, но всё равно ретраим — может,
            # тот процесс умрёт. Ставим бэк-офф побольше.
            log.error(
                "Telegram Conflict (другой процесс с тем же токеном?): %s "
                "— restart in %ds.", e, delay,
            )
        except Exception:
            log.exception(
                "Unexpected error in run_polling — restart in %ds.", delay,
            )

        # Если polling успел проработать стабильно — сбрасываем backoff.
        # Это лечит ситуацию «раз в день моргнул интернет на 1 секунду» —
        # не нужно выходить на 5-минутную паузу.
        uptime = time.time() - run_started_at
        if uptime >= POLLING_STABLE_RESET_SEC:
            delay = POLLING_RESTART_INITIAL_SEC

        log.info("Restart in %d sec...", delay)
        time.sleep(delay)
        delay = min(delay * 2, POLLING_RESTART_MAX_SEC)


def main() -> None:
    global _mesh_iface, MESHTASTIC_PORT

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        default=None,
        help="Serial port, e.g. COM3. Overrides MESHTASTIC_PORT in config.",
    )
    args = parser.parse_args()
    if args.port:
        MESHTASTIC_PORT = args.port

    if not BOT_TOKEN or BOT_TOKEN.startswith("PASTE_"):
        raise SystemExit(
            "Set BOT_TOKEN in relay.py. Create a NEW bot via @BotFather for the "
            "public relay (do not reuse the personal bot.py token)."
        )

    db_init()
    _mesh_iface = _connect_mesh()

    if _my_node_id == POCKET_NODE_ID:
        log.warning(
            "HOME (%s) == POCKET (%s). This machine is plugged into the pocket "
            "node itself; DMs will loop to ourselves. Check POCKET_NODE_ID.",
            _my_node_id, POCKET_NODE_ID,
        )

    _run_polling_with_retry()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        if _mesh_iface is not None:
            try:
                _mesh_iface.close()
            except Exception:
                pass
