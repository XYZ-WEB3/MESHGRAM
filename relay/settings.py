"""
Runtime settings stored in a `.env` file next to this module.

`.env` is the source of truth: GUI reads and writes it, `relay.py` loads it at
startup. `.env.example` lives in the repo as the template; real `.env` is in
`.gitignore` because it contains the bot token.

Layout:
    .env            — actual runtime values (not committed)
    .env.example    — template / defaults (committed)
    settings.py     — loader / saver / validator

Format is standard dotenv (KEY=VALUE, # comments, blank lines ignored).
String values with spaces or specials are double-quoted; backslash-escapes
for `\\`, `"` and `\\n`. List values (e.g. SOS_RECIPIENTS) are comma-separated.

load() always returns a dict with every key from DEFAULTS so callers can
index without None-checks.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any


def _resolve_app_dir() -> Path:
    """Папка для пользовательских данных. В frozen-сборке (.exe) — рядом
    с .exe. В обычном запуске — рядом с этим .py файлом.

    Не импортируем `paths.py` здесь чтобы settings.py не имел
    дополнительных зависимостей и оставался самодостаточным.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


_APP_DIR = _resolve_app_dir()
ENV_PATH: Path = _APP_DIR / ".env"
# .env.example — read-only template, ищем в bundle (для frozen) или
# рядом с скриптом (для source). Записывается через write_example()
# только в source-режиме.
_EXAMPLE_DIR = _APP_DIR
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", None)
    if _meipass:
        _EXAMPLE_DIR = Path(_meipass)
EXAMPLE_PATH: Path = _EXAMPLE_DIR / ".env.example"


# ---------------------------------------------------------------------------
# Schema — every key lives here. Type is inferred from the default value.
# ---------------------------------------------------------------------------
DEFAULTS: dict[str, Any] = {
    # --- Connection ---
    "bot_token":      "",
    "owner_id":       0,
    "pocket_node_id": "",
    "last_com_port":  "",

    # Язык GUI: "ru" / "en". Спрашивается на первом запуске в wizard'е.
    # Меняется через настройки. Релей-side тексты (что уходит в LoRa) не
    # затрагиваются — только UI на стороне пользователя.
    "gui_lang":       "ru",

    # Display name for the relay's recipient, shown to public users in bot
    # replies ("📨 Передаю Михаилу…", "Михаил: ..." etc). Default is "Михаил"
    # for the original author; rename if the bot is used by someone else.
    "display_name":   "Михаил",

    # --- Device (home node hardware) ---
    # generic | heltec_v3 | heltec_v3_1 | tbeam | tbeam_supreme | t_echo | t_deck | rak4631 | other
    "node_model":     "generic",

    # --- Mesh ---
    # hop_limit на исходящих DM. 1 = только прямая видимость (быстрее, без
    # ретрансляций). Поднять до 3 если pocket-нода может оказаться за углом
    # и нужны промежуточные ноды-ретрансляторы.
    "mesh_hop_limit": 1,

    # Режим доставки:
    #   "reliable" (default) — wantAck=True, есть «✓ Доставлено» / NAK,
    #     ретраи если не дошло. Чуть медленнее (ждём ACK ~1-3 с).
    #   "fast"               — wantAck=False, fire-and-forget. Никаких
    #     подтверждений, никаких retry, мгновенно. Подходит для коротких
    #     срочных сообщений когда «лишь бы быстрее, а не наверняка».
    "mesh_delivery_mode": "reliable",

    # --- Limits ---
    "max_text_length":        170,
    "slot_ttl_hours":         20,
    "slot_sticky_hours":      10,
    "max_username_in_prefix": 10,
    "pocket_fresh_min":       10,
    "pocket_stale_min":       60,

    # --- GPS (BETA) ---
    "gps_enabled":          False,
    "gps_fix_fresh_min":    5,
    "gps_fix_stale_min":    30,
    "gps_fix_max_min":      120,
    "where_rate_limit_min": 5,

    # --- Access ---
    "whitelist_enabled": False,

    # --- SOS (flat — easier .env mapping) ---
    "sos_enabled":        False,
    "sos_message":        "🆘 Михаилу нужна помощь. Это автоматическое уведомление.",
    "sos_include_coords": True,
    "sos_recipients":     [],  # list[int]

    # --- Delivery status / retry ---
    "retry_initial_delay_min":  2,
    "retry_max_interval_min":   15,

    # --- Logging ---
    # Файл relay.log пишется рядом со скриптом. При log_file_enabled=False
    # бот пишет только в stdout (что подхватит GUI/journalctl).
    "log_file_enabled": True,
    "log_file_max_mb":  5,    # размер одного файла перед ротацией
    "log_file_keep":    5,    # сколько бэкапов хранить (relay.log.1 .. .5)

    # --- AI helper (locally via LM Studio / Ollama / любой OpenAI-compatible) ---
    # Использование: с pocket-ноды напиши «@<TRIGGER> <вопрос>» — придёт ответ
    # на новом slot'е (@<TRIGGER>1, @<TRIGGER>2, ...). Продолжение диалога —
    # «@<TRIGGER>N <текст>», бот подтянет историю чата для контекста.
    # TRIGGER по умолчанию «ai», можно сменить (например на «gpt»).
    "ai_enabled":        False,
    # Тег команды на pocket-ноде. Меняется только в latin-буквах (a-z) —
    # иначе регексп для @<tag>N не сработает. Минимум 1 символ.
    "ai_trigger_tag":    "ai",
    # OpenAI-compatible base URL. LM Studio на дефолтном порту слушает 1234.
    "ai_base_url":       "http://localhost:1234/v1",
    # API key. LM Studio принимает любой непустой; для облачных провайдеров
    # ставь свой реальный.
    "ai_api_key":        "lm-studio",
    # Имя модели. В LM Studio это слаг загруженной модели (см. вкладку Models).
    "ai_model":          "llama-3.2-8b-instruct",
    # Системный промпт — задаёт тон и краткость. Меняй под свою задачу.
    "ai_system_prompt":  "Отвечай коротко и ясно. Максимум 2-3 предложения. "
                         "Без лишних объяснений и приветствий.",
    # Таймаут одного запроса. На локальной модели обычно 5-15 сек.
    "ai_timeout_sec":    30,
    # Сколько последних пар user/assistant включать в контекст (помимо system).
    "ai_max_history":    10,
    # TTL диалога. После N часов неактивности slot ai_N освобождается.
    "ai_ttl_hours":      168,   # 7 дней
}


# Keys grouped for nice .env formatting.
GROUPS: list[tuple[str, list[str]]] = [
    ("Connection", ["bot_token", "owner_id", "pocket_node_id", "last_com_port",
                    "gui_lang",
                    "display_name", "node_model", "mesh_hop_limit",
                    "mesh_delivery_mode"]),
    ("Limits", ["max_text_length", "slot_ttl_hours", "slot_sticky_hours",
                "max_username_in_prefix", "pocket_fresh_min", "pocket_stale_min"]),
    ("GPS (BETA — not tested by author)", [
        "gps_enabled", "gps_fix_fresh_min", "gps_fix_stale_min",
        "gps_fix_max_min", "where_rate_limit_min",
    ]),
    ("Access", ["whitelist_enabled"]),
    ("SOS", ["sos_enabled", "sos_message", "sos_include_coords", "sos_recipients"]),
    ("Delivery / retry", ["retry_initial_delay_min", "retry_max_interval_min"]),
    ("Logging", ["log_file_enabled", "log_file_max_mb", "log_file_keep"]),
    ("AI helper (LM Studio / Ollama / OpenAI-compatible)", [
        "ai_enabled", "ai_trigger_tag", "ai_base_url", "ai_api_key",
        "ai_model", "ai_system_prompt",
        "ai_timeout_sec", "ai_max_history", "ai_ttl_hours",
    ]),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def load() -> dict[str, Any]:
    """Read .env, cast each value to its schema type, merge with DEFAULTS."""
    out = copy.deepcopy(DEFAULTS)
    if not ENV_PATH.exists():
        return out
    try:
        raw = _parse_env(ENV_PATH.read_text(encoding="utf-8"))
    except OSError:
        return out
    for key, default in DEFAULTS.items():
        env_key = key.upper()
        if env_key not in raw:
            continue
        out[key] = _coerce(raw[env_key], default)
    return out


def save(data: dict[str, Any]) -> None:
    """Write .env atomically with comments, grouping and proper escaping."""
    merged = copy.deepcopy(DEFAULTS)
    merged.update({k: data[k] for k in DEFAULTS if k in data})

    lines: list[str] = [
        "# Meshtastic ↔ Telegram Relay — runtime settings.",
        "# Edit via the GUI (Настройки → Открыть настройки…) or by hand.",
        "# DO NOT COMMIT — this file contains the bot token.",
        "",
    ]
    for group_name, keys in GROUPS:
        lines.append(f"# --- {group_name} ---")
        for k in keys:
            if k in merged:
                lines.append(f"{k.upper()}={_format_value(merged[k])}")
        lines.append("")
    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(ENV_PATH)


def write_example() -> None:
    """Write .env.example with empty placeholders for all keys."""
    blank = copy.deepcopy(DEFAULTS)
    blank["bot_token"] = "PASTE_BOT_TOKEN_HERE"
    blank["owner_id"] = 0
    blank["pocket_node_id"] = ""
    lines: list[str] = [
        "# Meshtastic ↔ Telegram Relay — template .env.",
        "# Copy this to .env and fill in values (or use the GUI).",
        "",
    ]
    for group_name, keys in GROUPS:
        lines.append(f"# --- {group_name} ---")
        for k in keys:
            if k in blank:
                lines.append(f"{k.upper()}={_format_value(blank[k])}")
        lines.append("")
    EXAMPLE_PATH.write_text("\n".join(lines), encoding="utf-8")


def exists() -> bool:
    return ENV_PATH.exists()


def validate(data: dict[str, Any]) -> list[str]:
    """Return list of human-readable error strings. Empty list = OK."""
    errs: list[str] = []
    s = copy.deepcopy(DEFAULTS)
    s.update({k: data[k] for k in DEFAULTS if k in data})

    tok = s["bot_token"]
    if not tok:
        errs.append("Не задан токен бота (BotFather → /newbot).")
    elif ":" not in tok or len(tok) < 30:
        errs.append("Токен выглядит некорректно — должен быть формата 'NNNNN:XXXX...'.")

    try:
        oid = int(s["owner_id"])
    except (TypeError, ValueError):
        errs.append("OWNER_ID должен быть числом (узнай через @my_id_bot).")
        oid = 0
    if oid <= 0:
        errs.append("OWNER_ID не задан (узнай через @my_id_bot).")

    pid = (s["pocket_node_id"] or "").strip()
    if not pid:
        errs.append("Не задан ID карманной ноды (формат: !xxxxxxxx).")
    elif not (pid.startswith("!") and len(pid) == 9
              and all(c in "0123456789abcdefABCDEF" for c in pid[1:])):
        errs.append("ID карманной ноды должен быть формата !xxxxxxxx (8 hex-знаков).")

    recips = s.get("sos_recipients") or []
    if not isinstance(recips, list):
        errs.append("SOS_RECIPIENTS должен быть списком (через запятую в .env).")
    else:
        for x in recips:
            try:
                int(x)
            except (TypeError, ValueError):
                errs.append(f"SOS recipient '{x}' — не число.")

    for key in ("max_text_length", "slot_ttl_hours", "slot_sticky_hours",
                "pocket_fresh_min", "pocket_stale_min",
                "gps_fix_fresh_min", "gps_fix_stale_min", "gps_fix_max_min",
                "where_rate_limit_min", "retry_initial_delay_min",
                "retry_max_interval_min",
                "log_file_max_mb", "log_file_keep",
                "mesh_hop_limit",
                "ai_timeout_sec", "ai_max_history", "ai_ttl_hours"):
        try:
            v = int(s[key])
            if v < 0:
                errs.append(f"{key} не может быть отрицательным.")
        except (TypeError, ValueError):
            errs.append(f"{key} должно быть числом.")

    mode = str(s.get("mesh_delivery_mode") or "reliable").lower()
    if mode not in ("reliable", "fast"):
        errs.append("MESH_DELIVERY_MODE должен быть 'reliable' или 'fast'.")

    return errs


# ---------------------------------------------------------------------------
# Internal — .env I/O
# ---------------------------------------------------------------------------
def _parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        out[k.strip()] = _unquote(v.strip())
    return out


def _unquote(v: str) -> str:
    """Strip surrounding quotes and decode \\ \" \\n escapes."""
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
        # Reverse the escape sequence used in _format_value.
        out = []
        i = 0
        while i < len(v):
            if v[i] == "\\" and i + 1 < len(v):
                nxt = v[i + 1]
                if nxt == "n":
                    out.append("\n")
                elif nxt == '"':
                    out.append('"')
                elif nxt == "\\":
                    out.append("\\")
                else:
                    out.append(v[i:i + 2])
                i += 2
            else:
                out.append(v[i])
                i += 1
        return "".join(out)
    if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
        return v[1:-1]
    return v


def _coerce(raw: str, default: Any) -> Any:
    """Cast raw string from .env to the type of the default value."""
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default
    if isinstance(default, list):
        # Comma-separated list of ints (only list type we use right now).
        if not raw.strip():
            return []
        parts = [x.strip() for x in raw.split(",") if x.strip()]
        out = []
        for p in parts:
            try:
                out.append(int(p))
            except ValueError:
                pass
        return out
    return raw


def _format_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    s = str(v)
    # Always double-quote strings with any special chars, to be safe.
    needs_quote = any(c in s for c in (' ', '\t', '"', "'", '\n', '#', '='))
    if not needs_quote and s != "":
        return s
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
