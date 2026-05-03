"""
Read/write helpers для GUI-стороны. Используется gui.py и dialogs.py.
relay.py владеет тем же SQLite-файлом в runtime — эти функции открывают
кратковременные соединения, поэтому конкурентный доступ безопасен.

DB_PATH через paths.APP_DATA_DIR — критично для PyInstaller-сборки:
- В source-mode: рядом с db.py = relay/relay.db ✓
- В frozen-mode (.exe): __file__ указывает на _MEIxxxx/db.py (распакованный
  временный bundle), и `Path(__file__).with_name("relay.db")` дал бы
  _MEIxxxx/relay.db — это пустой файл, GUI бы ничего там не видел.
  Через APP_DATA_DIR — рядом с .exe, тот же файл что использует relay.py.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import paths as _paths

DB_PATH: Path = _paths.APP_DATA_DIR / "relay.db"


# ---------------------------------------------------------------------------
def _connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def bootstrap() -> None:
    """Create an empty relay.db with just enough tables for GUI-only edits."""
    conn = _connect()
    try:
        conn.executescript(
            """
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
            CREATE TABLE IF NOT EXISTS favorites (
                tg_user_id INTEGER PRIMARY KEY,
                added_at   INTEGER NOT NULL,
                note       TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                tag        TEXT NOT NULL UNIQUE,
                created_at INTEGER NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------- users ----------
def list_users() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        conn = _connect(readonly=True)
        try:
            cur = conn.execute(
                "SELECT u.tg_user_id, u.tg_username, u.first_name, "
                "u.banned, u.whitelisted, u.first_seen, u.last_seen, "
                "u.entry_tag, "
                "EXISTS(SELECT 1 FROM favorites f WHERE f.tg_user_id = u.tg_user_id) AS is_fav "
                "FROM users u ORDER BY u.last_seen DESC"
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def ensure_user(tg_id: int, name: str | None = None) -> None:
    if not DB_PATH.exists():
        bootstrap()
    conn = _connect()
    try:
        now = int(time.time())
        cur = conn.execute("SELECT 1 FROM users WHERE tg_user_id = ?", (tg_id,))
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO users (tg_user_id, tg_username, first_name, banned, "
                "whitelisted, entry_tag, first_seen, last_seen) "
                "VALUES (?, NULL, ?, 0, 0, NULL, ?, ?)",
                (tg_id, name, now, now),
            )
        elif name:
            conn.execute(
                "UPDATE users SET first_name = COALESCE(first_name, ?) "
                "WHERE tg_user_id = ?",
                (name, tg_id),
            )
        conn.commit()
    finally:
        conn.close()


def set_flag(tg_id: int, column: str, value: bool) -> None:
    if column not in ("banned", "whitelisted"):
        raise ValueError(column)
    conn = _connect()
    try:
        conn.execute(
            f"UPDATE users SET {column} = ? WHERE tg_user_id = ?",
            (1 if value else 0, tg_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_fav(tg_id: int, fav: bool) -> None:
    conn = _connect()
    try:
        if fav:
            conn.execute(
                "INSERT OR IGNORE INTO favorites (tg_user_id, added_at, note) "
                "VALUES (?, ?, NULL)",
                (tg_id, int(time.time())),
            )
        else:
            conn.execute("DELETE FROM favorites WHERE tg_user_id = ?", (tg_id,))
        conn.commit()
    finally:
        conn.close()


def set_entry_tag(tg_id: int, tag: str | None) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE users SET entry_tag = ? WHERE tg_user_id = ?",
            (tag, tg_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(tg_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM users WHERE tg_user_id = ?", (tg_id,))
        conn.execute("DELETE FROM favorites WHERE tg_user_id = ?", (tg_id,))
        conn.execute("DELETE FROM slots WHERE tg_user_id = ?", (tg_id,))
        conn.commit()
    finally:
        conn.close()


# ---------- categories ----------
def list_categories() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        conn = _connect(readonly=True)
        try:
            cur = conn.execute(
                "SELECT id, name, tag, created_at FROM categories ORDER BY name"
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def add_category(name: str, tag: str) -> bool:
    """Return True if added, False if tag exists."""
    if not DB_PATH.exists():
        bootstrap()
    conn = _connect()
    try:
        cur = conn.execute("SELECT 1 FROM categories WHERE tag = ?", (tag.lower(),))
        if cur.fetchone():
            return False
        conn.execute(
            "INSERT INTO categories (name, tag, created_at) VALUES (?, ?, ?)",
            (name.strip(), tag.strip().lower(), int(time.time())),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def remove_category(tag: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM categories WHERE tag = ?", (tag.strip().lower(),))
        conn.commit()
    finally:
        conn.close()


# ---------- slots / status indicators ----------
def active_slots_count() -> int | None:
    if not DB_PATH.exists():
        return None
    try:
        conn = _connect(readonly=True)
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM slots WHERE expires_at >= ?",
                (int(time.time()),),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def list_active_slots() -> list[dict]:
    if not DB_PATH.exists():
        return []
    try:
        conn = _connect(readonly=True)
        try:
            # Tolerate older schemas that lack last_message: pull "*" then guard.
            cur = conn.execute("PRAGMA table_info(slots)")
            cols = {row["name"] for row in cur.fetchall()}
            has_msg = "last_message" in cols
            select_msg = "s.last_message AS last_message" if has_msg else "NULL AS last_message"
            cur = conn.execute(
                f"SELECT s.slot_n, s.tg_user_id, s.created_at, s.expires_at, "
                f"COALESCE(s.was_replied, 0) AS was_replied, "
                f"{select_msg}, "
                "u.tg_username, u.first_name, u.entry_tag "
                "FROM slots s LEFT JOIN users u USING (tg_user_id) "
                "WHERE s.expires_at >= ? ORDER BY s.expires_at",
                (int(time.time()),),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


def gps_summary() -> dict:
    out = {"have_fix": False, "age_min": None, "fav_count": None}
    if not DB_PATH.exists():
        return out
    try:
        conn = _connect(readonly=True)
        try:
            cur = conn.execute(
                "SELECT lat, lon, fix_time, received_at FROM gps_position WHERE id = 1"
            )
            row = cur.fetchone()
            if row:
                ts = row[2] or row[3]
                if ts:
                    out["have_fix"] = True
                    out["age_min"] = max(0, int((time.time() - ts) / 60))
            cur = conn.execute("SELECT COUNT(*) FROM favorites")
            row = cur.fetchone()
            if row:
                out["fav_count"] = int(row[0])
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return out
