# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec для Meshgram (GUI + relay в одном .exe).

Сборка:
    cd relay
    pyinstaller Meshgram.spec --clean

Результат:
    dist/Meshgram.exe   — onefile, без консоли, с иконкой и SVG-ассетами

Команда юзера: двойной клик по Meshgram.exe → запускается GUI с tray.
Релей живёт как QProcess внутри GUI — отдельного relay.exe не нужно.
"""
from pathlib import Path

block_cipher = None

# Корневая папка spec'а
ROOT = Path(SPECPATH).resolve()


# ─── 1. Точка входа ───────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Иконка для tray и QIcon-fallback
        (str(ROOT / "assets" / "icon.svg"), "assets"),
        (str(ROOT / "assets" / "icon.png"), "assets"),
        # Папка с SVG-моделями нод (50 штук, нужны для node-picker)
        (str(ROOT / "devices"), "devices"),
        # relay.py — стартуется через QProcess из GUI, должен быть в bundle
        (str(ROOT / "relay.py"), "."),
        # Helper-модули которые relay.py импортирует
        (str(ROOT / "ai_helper.py"), "."),
        (str(ROOT / "settings.py"), "."),
        (str(ROOT / "db.py"), "."),
        (str(ROOT / "dialogs.py"), "."),
        (str(ROOT / "icons.py"), "."),
        (str(ROOT / "theme.py"), "."),
        (str(ROOT / "widgets.py"), "."),
        # .env.example — чтоб юзер мог скопировать-настроить
        (str(ROOT / ".env.example"), "."),
    ],
    hiddenimports=[
        # PyInstaller иногда не находит эти подмодули автоматически
        "meshtastic.serial_interface",
        "meshtastic.protobuf",
        "telegram.ext",
        "telegram.error",
        "pubsub",
        "pubsub.core",
        "serial.tools.list_ports",
        # AI helper — ленивый, но добавим в bundle
        "openai",
        "openai._client",
        # Pillow / SVG для иконки
        "PIL.Image",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Не нужны в нашем .exe — экономим размер
        "tkinter",
        "test",
        "unittest",
        "pytest",
        # Конфликт: в системе может быть PyQt5 как косвенная зависимость
        # (matplotlib, scientific Python). PyInstaller не любит когда
        # одновременно находятся PyQt5 и PyQt6.
        "PyQt5",
        "PySide2",
        "PySide6",
        # Тяжёлые научные либы которые вытягиваются транзитивно — нам не нужны
        "matplotlib",
        "scipy",
        "numpy.core._dotblas",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "nbformat",
        "nbconvert",
        "zmq",
        "tornado",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Meshgram",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX-pack отключаем — иногда AV-false-positive
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                  # ← НЕТ консоли (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),  # иконка .exe в проводнике/таскбаре
)
