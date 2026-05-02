#!/usr/bin/env python3
"""
Meshgram Relay — main PyQt6 window.

Структура:
    menubar  : Файл / Правка / Вид / Сервис / Справка
    toolbar  : Start/Stop · Restart · COM-port · Settings/Users/Slots/Categories · search · pause/clear
    body     : QSplitter — лог слева, правая панель (NodePanel + активные слоты)
    statusbar: StatusCell-ячейки с GlowDot

Процесс relay.py запускается как QProcess; стандартные потоки идут в LogConsole.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import serial.tools.list_ports
from PyQt6.QtCore import (
    QProcess,
    QProcessEnvironment,
    QSharedMemory,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# Make sibling modules importable when launched from a different cwd.
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import db
import i18n_gui
import settings as settings_mod
from dialogs import (
    AboutDialog,
    OnboardingDialog,
    SettingsDialog,
    SlotsDialog,
    UsersDialog,
)
from i18n_gui import t as _t
from icons import make_icon
from theme import PALETTE, apply_theme
from widgets import GlowDot, LogConsole, NodePanel, StatusCell, ToolBtn, ToolSep

RELAY_SCRIPT = SCRIPT_DIR / "relay.py"


def _is_frozen() -> bool:
    """True если запущены из PyInstaller .exe."""
    return getattr(sys, "frozen", False)


def _relay_command() -> tuple[str, list[str]]:
    """Возвращает (program, args) для запуска relay-процесса.

    Frozen .exe: запускаем себя же с флагом --relay (один бинарник, два режима).
    Source: запускаем интерпретатор с relay.py.
    """
    if _is_frozen():
        # sys.executable указывает на Meshgram.exe — запускаем его с --relay
        return (sys.executable, ["--relay"])
    # Source-mode — обычный запуск
    return (sys.executable, [str(RELAY_SCRIPT)])


class Relay(QMainWindow):
    POLL_MS = 2000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Meshgram Relay")
        self.resize(1280, 820)
        self.setMinimumSize(1100, 700)
        self.process: Optional[QProcess] = None
        self._cfg = settings_mod.load()
        self._quit_requested = False   # True если выход через tray-menu / Cmd+Q

        # App-level icon (для taskbar / tray). Берём mark.svg из бренд-папки;
        # если её нет (например в распакованном .exe — bundle-папка другая),
        # fallback на стандартную иконку Qt.
        app_icon = self._load_app_icon()
        self.setWindowIcon(app_icon)

        self._build_menu()
        self._build_central()
        self._build_statusbar()
        self._refresh_ports()
        self._refresh_status()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start(self.POLL_MS)

        # System tray
        self._tray: Optional[QSystemTrayIcon] = None
        self._setup_tray(app_icon)

        # Hot keys
        QShortcut(QKeySequence("F5"), self, activated=self._start)
        QShortcut(QKeySequence("Shift+F5"), self, activated=self._stop)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self._open_users)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=self._open_slots)
        QShortcut(QKeySequence("Space"), self, activated=self._toggle_pause)

        # First run
        if not settings_mod.exists():
            QTimer.singleShot(200, self._first_run)

    # =====================================================================
    # Icon + system tray
    @staticmethod
    def _load_app_icon() -> QIcon:
        """Загрузить иконку приложения. Ищет в нескольких местах:
        1. bundle-data при PyInstaller-сборке (sys._MEIPASS/assets/icon.png)
        2. рядом со скриптом: relay/assets/icon.png
        3. фолбэк на стандартную системную иконку
        """
        candidates = []
        # PyInstaller onefile / onedir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "icon.png")
            candidates.append(Path(meipass) / "assets" / "icon.svg")
        # Standalone — рядом со скриптом
        candidates.append(SCRIPT_DIR / "assets" / "icon.png")
        candidates.append(SCRIPT_DIR / "assets" / "icon.svg")
        # Source layout — site/assets/logo/mark.svg
        candidates.append(SCRIPT_DIR.parent / "site" / "assets" / "logo" / "mark.svg")

        for path in candidates:
            if path.exists():
                icon = QIcon(str(path))
                if not icon.isNull():
                    return icon
        # Фолбэк на стандартную Qt-иконку
        app = QApplication.instance()
        if app is not None:
            return app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        return QIcon()

    def _setup_tray(self, icon: QIcon) -> None:
        """Создаёт QSystemTrayIcon с меню Show/Hide/Quit. Если трей в системе
        недоступен (редко на современных DE) — просто пропускаем."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        L = self._cfg.get("gui_lang", "ru")
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(_t("tray.tooltip", L))

        menu = QMenu(self)
        act_show = QAction(_t("tray.open", L), self, triggered=self._tray_show)
        act_start = QAction(_t("tray.start", L), self, triggered=self._start)
        act_stop = QAction(_t("tray.stop", L), self, triggered=self._stop)
        act_quit = QAction(_t("tray.quit", L), self, triggered=self._tray_quit)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_quit)
        self._tray.setContextMenu(menu)

        # Двойной клик / Click по иконке → показать
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._tray_show()

    def _tray_show(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_quit(self) -> None:
        """Полное закрытие приложения из tray-меню (минуя «свернуть в трей»)."""
        self._quit_requested = True
        self.close()

    # =====================================================================
    # Menu
    # =====================================================================
    def _build_menu(self) -> None:
        mb = self.menuBar()
        L = self._cfg.get("gui_lang", "ru")

        # File
        m_file = mb.addMenu(_t("menu.file", L))
        a_start = QAction(make_icon("play", color=PALETTE["t2"]), _t("act.start", L), self)
        a_start.setShortcut("F5")
        a_start.triggered.connect(self._start)
        m_file.addAction(a_start)
        a_stop = QAction(make_icon("stop", color=PALETTE["t2"]), _t("act.stop", L), self)
        a_stop.setShortcut("Shift+F5")
        a_stop.triggered.connect(self._stop)
        m_file.addAction(a_stop)
        a_restart = QAction(make_icon("refresh", color=PALETTE["t2"]), _t("act.restart", L), self)
        a_restart.setShortcut("Ctrl+R")
        a_restart.triggered.connect(self._restart)
        m_file.addAction(a_restart)
        m_file.addSeparator()
        a_quit = QAction(_t("act.quit", L), self)
        a_quit.setShortcut("Ctrl+Q")
        a_quit.triggered.connect(self.close)
        m_file.addAction(a_quit)

        # Edit
        m_edit = mb.addMenu(_t("menu.edit", L))
        a_clear = QAction(make_icon("trash", color=PALETTE["t2"]), _t("act.clear_log", L), self)
        a_clear.triggered.connect(lambda: self.console.clear_log())
        m_edit.addAction(a_clear)

        # View
        m_view = mb.addMenu(_t("menu.view", L))
        self._a_pause = QAction(make_icon("pause", color=PALETTE["t2"]),
                                _t("act.pause_scroll", L), self)
        self._a_pause.setShortcut("Space")
        self._a_pause.setCheckable(True)
        self._a_pause.triggered.connect(self._toggle_pause)
        m_view.addAction(self._a_pause)
        a_slots = QAction(make_icon("inbox", color=PALETTE["t2"]), _t("act.slots", L), self)
        a_slots.setShortcut("Ctrl+1")
        a_slots.triggered.connect(self._open_slots)
        m_view.addAction(a_slots)

        # Tools
        m_tools = mb.addMenu(_t("menu.tools", L))
        a_settings = QAction(make_icon("settings", color=PALETTE["t2"]),
                             _t("act.settings", L), self)
        a_settings.setShortcut("Ctrl+,")
        a_settings.triggered.connect(self._open_settings)
        m_tools.addAction(a_settings)
        a_users = QAction(make_icon("users", color=PALETTE["t2"]), _t("act.users", L), self)
        a_users.setShortcut("Ctrl+U")
        a_users.triggered.connect(self._open_users)
        m_tools.addAction(a_users)
        a_cats = QAction(make_icon("cat", color=PALETTE["t2"]), _t("act.cats", L), self)
        a_cats.triggered.connect(lambda: self._open_settings("cats"))
        m_tools.addAction(a_cats)

        # Help
        m_help = mb.addMenu(_t("menu.help", L))
        a_about = QAction(_t("act.about", L), self)
        a_about.triggered.connect(self._open_about)
        m_help.addAction(a_about)
        a_id = QAction(_t("act.id_help", L), self)
        a_id.triggered.connect(self._show_id_help)
        m_help.addAction(a_id)
        a_site = QAction(make_icon("link", color=PALETTE["t2"]), _t("act.site", L), self)
        a_site.triggered.connect(lambda: self._open_url("https://meshgram.site"))
        m_help.addAction(a_site)

    def _open_url(self, url: str) -> None:
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # =====================================================================
    # Central widget — toolbar + body splitter
    # =====================================================================
    def _build_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── Toolbar ─────────────────────────────────────────────────
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setStyleSheet(
            f"QToolBar {{ background: {PALETTE['bg2']}; "
            f"border-bottom: 1px solid #14181d; padding: 4px 6px; spacing: 4px; }}"
            f"QToolBar QToolButton {{ background: transparent; color: {PALETTE['t2']}; "
            "border: 1px solid transparent; border-radius: 3px; padding: 4px 8px; }}"
            f"QToolBar QToolButton:hover {{ background: {PALETTE['bg4']}; color: {PALETTE['t1']}; }}"
        )

        self.btn_start = ToolBtn("play", "Старт", role="primary")
        self.btn_start.clicked.connect(self._start)
        tb.addWidget(self.btn_start)

        self.btn_stop = ToolBtn("stop", "Стоп", role="danger")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setEnabled(False)
        tb.addWidget(self.btn_stop)

        self.btn_restart = ToolBtn("refresh", "Перезапуск")
        self.btn_restart.setProperty("role", "ghost")
        self.btn_restart.clicked.connect(self._restart)
        self.btn_restart.setEnabled(False)
        tb.addWidget(self.btn_restart)

        tb.addWidget(ToolSep())

        # COM port
        port_row = QWidget()
        pl = QHBoxLayout(port_row)
        pl.setContentsMargins(4, 0, 4, 0)
        pl.setSpacing(6)
        usb_lbl = QLabel()
        usb_lbl.setPixmap(make_icon("usb", color=PALETTE["t3"], size=14).pixmap(14, 14))
        pl.addWidget(usb_lbl)
        pl.addWidget(QLabel("Порт:"))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(260)
        pl.addWidget(self.port_combo)
        ref_btn = ToolBtn("refresh", "")
        ref_btn.setProperty("role", "ghost")
        ref_btn.setFixedWidth(28)
        ref_btn.setToolTip("Сканировать порты")
        ref_btn.clicked.connect(self._refresh_ports)
        pl.addWidget(ref_btn)
        tb.addWidget(port_row)

        tb.addWidget(ToolSep())

        b_settings = ToolBtn("settings", "Настройки")
        b_settings.clicked.connect(self._open_settings)
        tb.addWidget(b_settings)

        b_users = ToolBtn("users", "Пользователи")
        b_users.clicked.connect(self._open_users)
        tb.addWidget(b_users)

        b_slots = ToolBtn("inbox", "Слоты")
        b_slots.clicked.connect(self._open_slots)
        tb.addWidget(b_slots)

        b_cats = ToolBtn("cat", "Категории")
        b_cats.clicked.connect(lambda: self._open_settings("cats"))
        tb.addWidget(b_cats)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.btn_pause = ToolBtn("pause", "")
        self.btn_pause.setProperty("role", "ghost")
        self.btn_pause.setCheckable(True)
        self.btn_pause.setFixedWidth(28)
        self.btn_pause.setToolTip("Пауза автопрокрутки лога")
        self.btn_pause.toggled.connect(self._on_pause_toggle)
        tb.addWidget(self.btn_pause)

        self.btn_clear = ToolBtn("trash", "")
        self.btn_clear.setProperty("role", "ghost")
        self.btn_clear.setFixedWidth(28)
        self.btn_clear.setToolTip("Очистить лог")
        self.btn_clear.clicked.connect(lambda: self.console.clear_log())
        tb.addWidget(self.btn_clear)

        v.addWidget(tb)

        # ── Body splitter ──────────────────────────────────────────
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(4)
        body.setChildrenCollapsible(False)

        # Left side — log + small log header
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 4, 8)
        lv.setSpacing(6)

        log_head = QHBoxLayout()
        log_head.setContentsMargins(2, 0, 2, 0)
        log_head.setSpacing(6)
        self._log_dot = GlowDot("off")
        log_head.addWidget(self._log_dot)
        log_lbl = QLabel("консоль")
        log_lbl.setStyleSheet(
            f"color: {PALETTE['t2']}; font-size: 11px; letter-spacing: 1px;"
        )
        log_head.addWidget(log_lbl)
        log_head.addStretch(1)
        # Keep a hidden line counter for internal bookkeeping (used by other code).
        self._log_count_lbl = QLabel("")
        self._log_count_lbl.hide()
        log_head.addWidget(self._log_count_lbl)
        lv.addLayout(log_head)

        self.console = LogConsole()
        lv.addWidget(self.console, 1)

        body.addWidget(left)

        # Right side — info panel
        right = QFrame()
        right.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; border-left: 1px solid {PALETTE['hl1']}; }}"
        )
        rv = QVBoxLayout(right)
        rv.setContentsMargins(10, 10, 10, 10)
        rv.setSpacing(10)

        self.node_panel = NodePanel()
        rv.addWidget(self.node_panel)

        slots_head = QLabel("СЛОТЫ @N")
        slots_head.setStyleSheet(
            f"color: {PALETTE['t3']}; font-size: 10px; letter-spacing: 1px; "
            "font-weight: 600; text-transform: uppercase;"
        )
        rv.addWidget(slots_head)

        self.slots_list = QListWidget()
        self.slots_list.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg2']}; border: none; "
            f"font-family: 'Consolas', monospace; font-size: 11px; }}"
            "QListWidget::item { padding: 4px 6px; }"
        )
        rv.addWidget(self.slots_list, 1)

        open_slots_btn = ToolBtn("list", "Открыть таблицу слотов")
        open_slots_btn.setProperty("role", "ghost")
        open_slots_btn.clicked.connect(self._open_slots)
        rv.addWidget(open_slots_btn)

        body.addWidget(right)
        body.setStretchFactor(0, 3)
        body.setStretchFactor(1, 1)
        body.setSizes([900, 320])
        v.addWidget(body, 1)

    # =====================================================================
    # Status bar — минимум: что важно пользователю, без dev-телеметрии.
    # =====================================================================
    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)

        self.sc_bot   = StatusCell("Бот: остановлен",  tone="off")
        self.sc_node  = StatusCell("Нода: нет",        tone="off")
        self.sc_slots = StatusCell("Слоты: —",         tone="off")
        # Опциональные ячейки — показываем только когда ВКЛ.
        self.sc_gps   = StatusCell("GPS β",            tone="off")
        self.sc_sos   = StatusCell("SOS",              tone="off")
        self.sc_wl    = StatusCell("Закрытый режим",   tone="off", with_dot=False)

        self.sc_slots.clicked.connect(self._open_slots)
        self.sc_gps.clicked.connect(lambda: self._open_settings("gps"))
        self.sc_sos.clicked.connect(lambda: self._open_settings("sos"))
        self.sc_wl.clicked.connect(lambda: self._open_settings("wl"))
        self.sc_bot.clicked.connect(lambda: self._open_settings("bot"))
        self.sc_node.clicked.connect(lambda: self._open_settings("pocket"))

        for w in (self.sc_bot, self.sc_node, self.sc_slots,
                  self.sc_gps, self.sc_sos, self.sc_wl):
            sb.addWidget(w)
        # Доменчик в правом углу — мелкая «подпись».
        self.sc_brand = StatusCell("meshgram.site", tone="off", with_dot=False)
        sb.addPermanentWidget(self.sc_brand)

    # =====================================================================
    # COM ports
    # =====================================================================
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentData()
        self.port_combo.clear()
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            self.port_combo.addItem("(портов не найдено)", None)
            self.port_combo.setEnabled(False)
            return
        self.port_combo.setEnabled(True)
        for p in ports:
            self.port_combo.addItem(f"{p.device}  ·  {p.description or ''}", p.device)
        target = current or settings_mod.load().get("last_com_port")
        if target:
            idx = self.port_combo.findData(target)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
                return
        for i in range(self.port_combo.count()):
            t = self.port_combo.itemText(i).lower()
            if any(k in t for k in ("usb", "silicon", "cp210", "ch340", "serial")):
                self.port_combo.setCurrentIndex(i)
                break

    # =====================================================================
    # Status / polling
    # =====================================================================
    def _refresh_status(self) -> None:
        self._cfg = settings_mod.load()
        errs = settings_mod.validate(self._cfg)
        running = self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

        # Бот — статус сводный: зелёный если запущен, красный если конфиг битый,
        # серый если просто остановлен.
        if running:
            self.sc_bot.setLabel("Бот: работает")
            self.sc_bot.setTone("ok", live=True)
        elif errs:
            self.sc_bot.setLabel(f"Бот: настрой ({len(errs)} ошиб.)")
            self.sc_bot.setTone("err", live=False)
        else:
            self.sc_bot.setLabel("Бот: остановлен")
            self.sc_bot.setTone("off", live=False)

        # Нода — пока без отдельного сигнала живой связи (внутренние данные
        # в подпроцессе); ориентируемся на то, что бот запущен и порт указан.
        port = self.port_combo.currentData() or ""
        if running and port:
            self.sc_node.setLabel(f"Нода: {port}")
            self.sc_node.setTone("ok", live=True)
        elif port:
            self.sc_node.setLabel(f"Нода: {port}")
            self.sc_node.setTone("off", live=False)
        else:
            self.sc_node.setLabel("Нода: порт не выбран")
            self.sc_node.setTone("warn", live=False)

        # Слоты
        n = db.active_slots_count()
        if n is None:
            self.sc_slots.setLabel("Слоты: —")
            self.sc_slots.setTone("off", live=False)
        else:
            self.sc_slots.setLabel(f"Слоты: {n}")
            self.sc_slots.setTone("info" if n > 0 else "off", live=n > 0)

        # GPS — показываем только если включено
        if self._cfg.get("gps_enabled"):
            self.sc_gps.show()
            info = db.gps_summary()
            if not info["have_fix"]:
                self.sc_gps.setLabel("GPS β: нет фикса")
                self.sc_gps.setTone("warn", live=False)
            else:
                age = info["age_min"] or 0
                if age <= int(self._cfg.get("gps_fix_fresh_min") or 5):
                    tone = "ok"
                elif age <= int(self._cfg.get("gps_fix_stale_min") or 30):
                    tone = "warn"
                else:
                    tone = "err"
                self.sc_gps.setLabel(f"GPS β: {age} мин назад")
                self.sc_gps.setTone(tone, live=False)
        else:
            self.sc_gps.hide()

        # SOS — только если включено
        if self._cfg.get("sos_enabled"):
            self.sc_sos.show()
            n_recip = len(self._cfg.get("sos_recipients") or [])
            self.sc_sos.setLabel(f"SOS активен · {n_recip}")
            self.sc_sos.setTone("err", live=True)
        else:
            self.sc_sos.hide()

        # Whitelist — только если включён
        if self._cfg.get("whitelist_enabled"):
            self.sc_wl.show()
            self.sc_wl.setLabel("Закрытый режим")
        else:
            self.sc_wl.hide()

        # Log dot
        self._log_dot.setTone("ok" if running else "off")
        self._log_dot.setLive(running)

        # node panel
        self.node_panel.update_state(
            com_port=port or "—",
            node_id=self._cfg.get("pocket_node_id") or "—",
            model_id=self._cfg.get("node_model") or "generic",
            slots=n if n is not None else 0,
            wl=bool(self._cfg.get("whitelist_enabled")),
            running=running,
        )

        # Active slots compact list
        self._refresh_slots_list()

        # Log line count
        line_count = self.console.document().blockCount()
        self._log_count_lbl.setText(f"{line_count} строк")

        # Start button enabled iff config valid
        self.btn_start.setEnabled(not errs and not running)
        self.btn_stop.setEnabled(running)
        self.btn_restart.setEnabled(running)
        self.port_combo.setEnabled(not running)

    def _refresh_slots_list(self) -> None:
        slots = db.list_active_slots()[:8]
        self.slots_list.clear()
        if not slots:
            it = QListWidgetItem("слотов нет")
            it.setForeground(QColor(PALETTE["t4"]))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.slots_list.addItem(it)
            return
        now = int(time.time())
        for s in slots:
            slot_n = s["slot_n"]
            name = s.get("tg_username") or s.get("first_name") or str(s["tg_user_id"])
            tag = s.get("entry_tag")
            label = f"@{slot_n}  {tag}:{name}" if tag else f"@{slot_n}  {name}"
            remaining = max(0, s["expires_at"] - now)
            hh = remaining // 3600
            mm = (remaining % 3600) // 60
            mark = " ★" if s.get("was_replied") else ""
            text = f"{label}{mark}    {hh:02d}:{mm:02d}"
            it = QListWidgetItem(text)
            tone_color = (
                QColor(PALETTE["err"])  if remaining < 1800
                else QColor(PALETTE["warn"]) if remaining < 7200
                else QColor(PALETTE["t1"])
            )
            it.setForeground(tone_color)
            self.slots_list.addItem(it)

    # =====================================================================
    # Pause / autoscroll toggle
    # =====================================================================
    def _toggle_pause(self) -> None:
        self.btn_pause.toggle()

    def _on_pause_toggle(self, checked: bool) -> None:
        # LogConsole always autoscrolls when not paused; we just stop autoscroll.
        # (We don't have an explicit pause flag in LogConsole; keep behaviour simple.)
        self._a_pause.setChecked(checked)
        self.btn_pause.setIcon(make_icon("play" if checked else "pause", color=PALETTE["t2"]))

    # =====================================================================
    # Dialogs
    # =====================================================================
    def _open_settings(self, section: str = "bot") -> None:
        dlg = SettingsDialog(self, open_section=section)
        if dlg.exec() == 1:
            self._refresh_status()
            if self.process is not None:
                QMessageBox.information(
                    self, "Перезапуск",
                    "Настройки сохранены. Перезапусти релей, чтобы они применились "
                    "(меню Файл → Перезапустить).",
                )

    def _open_users(self) -> None:
        UsersDialog(self).exec()
        self._refresh_status()

    def _open_slots(self) -> None:
        SlotsDialog(self).exec()

    def _open_about(self) -> None:
        AboutDialog(self).exec()

    def _show_id_help(self) -> None:
        QMessageBox.information(
            self, "Telegram ID",
            "Открой в Telegram бота @my_id_bot, нажми /start.\n"
            "Бот ответит твоим numeric ID — скопируй число и используй в "
            "настройках (OWNER_ID, SOS-получатели, whitelist и т.д.).",
        )

    def _first_run(self) -> None:
        dlg = OnboardingDialog(self)
        dlg.exec()
        self._refresh_status()

    # =====================================================================
    # Process control
    # =====================================================================
    def _ts(self) -> str:
        return datetime.now().strftime("[%H:%M:%S] ")

    def _start(self) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        port = self.port_combo.currentData()
        if not port:
            QMessageBox.warning(self, "Порт", "Сначала выбери COM-порт.")
            return
        # В source-режиме проверяем что relay.py рядом. В frozen-mode
        # relay.py запекался в bundle, проверять его наличие на диске
        # не нужно (он внутри .exe).
        if not _is_frozen() and not RELAY_SCRIPT.exists():
            QMessageBox.critical(self, "relay.py", "relay.py не найден.")
            return
        cfg = settings_mod.load()
        errs = settings_mod.validate(cfg)
        if errs:
            QMessageBox.warning(
                self, "Конфиг неполный",
                "Заполни настройки перед запуском:\n\n" + "\n".join("• " + e for e in errs),
            )
            return

        cfg["last_com_port"] = port
        try:
            settings_mod.save(cfg)
        except OSError:
            pass

        self.console.append_raw(f"{self._ts()}▶ Запуск relay на {port}\n")
        self.process = QProcess()
        # В frozen-mode рабочая папка должна быть рядом с .exe
        # (там лежит .env / relay.db). В source — рядом со скриптами.
        from paths import APP_DATA_DIR
        self.process.setWorkingDirectory(str(APP_DATA_DIR))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(env)
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        program, base_args = _relay_command()
        self.process.start(program, base_args + ["--port", port])
        if not self.process.waitForStarted(3000):
            self.console.append_raw(f"{self._ts()}✗ Не удалось запустить процесс\n")
            self.process = None
            return
        self._refresh_status()

    def _stop(self) -> None:
        if not self.process:
            return
        self.console.append_raw(f"{self._ts()}■ Останавливаю...\n")
        self.process.terminate()
        QTimer.singleShot(3000, self._force_kill)

    def _restart(self) -> None:
        self._stop()
        QTimer.singleShot(1500, self._start)

    def _force_kill(self) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.console.append_raw(f"{self._ts()}⚠ Таймаут, убиваю\n")
            self.process.kill()

    def _on_stdout(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self.console.append_raw(data)

    def _on_stderr(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        self.console.append_raw(data)

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        tag = "✓" if exit_code == 0 else "✗"
        self.console.append_raw(f"{self._ts()}{tag} Процесс завершён (код {exit_code})\n\n")
        self.process = None
        self._refresh_status()

    def closeEvent(self, ev) -> None:
        L = self._cfg.get("gui_lang", "ru")

        # Если трей доступен и юзер закрывает крестиком — сворачиваем в трей
        # (релей продолжает работать). Полный выход — через tray-меню «Выйти».
        if (
            self._tray is not None
            and self._tray.isVisible()
            and not self._quit_requested
        ):
            ev.ignore()
            self.hide()
            # Один раз показываем уведомление что не закрылись, а свернулись.
            if not getattr(self, "_tray_notified", False):
                self._tray.showMessage(
                    _t("tray.minimize_title", L),
                    _t("tray.minimize_text", L),
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
                self._tray_notified = True
            return

        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            r = QMessageBox.question(
                self, _t("quit.relay_running.title", L),
                _t("quit.relay_running.text", L),
            )
            if r != QMessageBox.StandardButton.Yes:
                ev.ignore()
                self._quit_requested = False  # отмена
                return
            self.process.kill()
            self.process.waitForFinished(3000)
        # Скрываем трей перед закрытием — иначе он зависнет в systray
        if self._tray is not None:
            self._tray.hide()
        ev.accept()


# Уникальный ключ shared-memory для single-instance проверки. Если
# второй экземпляр пытается стартовать — он увидит что ключ занят и
# покажет окно уже работающего (через активацию tray, либо просто
# покажет MessageBox и выйдет).
_SINGLE_INSTANCE_KEY = "Meshgram-Relay-SingleInstance-v1"


def main() -> None:
    # ── Relay-mode: один и тот же бинарник может работать как GUI или
    # как relay-процесс. Это критично для PyInstaller .exe — внутри нет
    # отдельного python.exe, и GUI запускает себя же с --relay.
    if "--relay" in sys.argv:
        sys.argv.remove("--relay")
        # Импорт relay поздний — чтобы при обычном GUI-запуске не загружать
        # тяжёлые meshtastic/telegram модули.
        import relay as relay_module
        relay_module.main()
        return

    app = QApplication(sys.argv)
    app.setApplicationName("Meshgram")
    app.setApplicationDisplayName("Meshgram Relay")
    # Tray-режим: GUI можно скрыть в трей, app не должен умирать
    # когда последнее окно закрыто.
    app.setQuitOnLastWindowClosed(False)

    # Single-instance: пытаемся захватить shared memory. Если уже занято —
    # это второй запуск, показываем сообщение и выходим.
    shared = QSharedMemory(_SINGLE_INSTANCE_KEY)
    # На POSIX могут оставаться битые segments после краха — ловим и чистим.
    if shared.attach():
        shared.detach()
    if not shared.create(1):
        # Локализуем сообщение под язык пользователя из настроек
        # (если уже сохранён) или по дефолту RU.
        try:
            _lang = settings_mod.load().get("gui_lang", "ru")
        except Exception:
            _lang = "ru"
        QMessageBox.information(
            None, _t("single.title", _lang), _t("single.text", _lang),
        )
        sys.exit(0)

    apply_theme(app)
    w = Relay()
    w.show()

    # Держим shared memory live до выхода
    app._meshgram_shared_memory = shared    # type: ignore[attr-defined]
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
