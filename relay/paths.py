"""
Централизованное определение базовых путей для разных запусков:

- Source-mode (python relay.py / python gui.py):
    BASE_DIR = папка где лежит relay/ (рядом с .py)
    .env, relay.db, relay.log хранятся **рядом с скриптом**

- Frozen-mode (PyInstaller .exe):
    BASE_DIR = папка где лежит .exe (НЕ временная _MEIxxxx)
    .env, relay.db, relay.log хранятся **рядом с .exe**

Это позволяет:
1. Юзеру держать настройки рядом с .exe — переехал на новый ПК →
   скопировал папку с Meshgram.exe + .env, и оно работает
2. Не терять настройки при перезапуске .exe (раньше .env писался в
   _MEIxxxx — временная папка PyInstaller, она пересоздаётся)

Использование:
    from paths import APP_DATA_DIR, RESOURCE_DIR
    env_path = APP_DATA_DIR / ".env"            # ← пишем туда
    icon_path = RESOURCE_DIR / "assets" / "icon.png"  # ← читаем оттуда (bundle ОК)
"""
from __future__ import annotations

import sys
from pathlib import Path


def _is_frozen() -> bool:
    """True если запущены из PyInstaller-сборки."""
    return getattr(sys, "frozen", False)


def _app_data_dir() -> Path:
    """Папка для пользовательских данных, которые ДОЛЖНЫ ПЕРЕЖИВАТЬ
    перезапуски: .env, .db, .log.

    - В frozen режиме — рядом с .exe (sys.executable.parent)
    - В source режиме — папка relay/ (рядом с этим файлом)
    """
    if _is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _resource_dir() -> Path:
    """Папка для read-only ресурсов (иконки, SVG моделей нод):

    - В frozen режиме — sys._MEIPASS (распакованный bundle)
    - В source режиме — папка relay/
    """
    if _is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(__file__).resolve().parent


APP_DATA_DIR: Path = _app_data_dir()
RESOURCE_DIR: Path = _resource_dir()
IS_FROZEN: bool = _is_frozen()
