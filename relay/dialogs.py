"""
Dialogs — port of designer's modal screens.

  SettingsDialog  — sidebar nav + section forms (Bot/Pocket/Limits/GPS/SOS/Cats/WL)
  UsersDialog     — filter pills + table + right detail pane
  SlotsDialog     — same shape, focused on @N slots and TTL bars
  OnboardingDialog — 3-step first-run wizard
  AboutDialog     — small centered card
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QByteArray, QRegularExpression, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap, QRegularExpressionValidator
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import db
import i18n_gui
import settings as settings_mod
from i18n_gui import t as _t
from icons import make_icon
from theme import PALETTE
from widgets import Badge, GlowDot, ToolBtn, ToolSep


# ===========================================================================
# Helpers
# ===========================================================================
def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {PALETTE['t3']}; font-size: 10.5px; line-height: 140%;"
    )
    return lbl


def _heading(title: str, sub: str = "") -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 6)
    v.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color: {PALETTE['t1']}; font-size: 14px; font-weight: 600;"
    )
    v.addWidget(t)
    if sub:
        s = QLabel(sub)
        s.setStyleSheet(f"color: {PALETTE['t3']}; font-size: 11px;")
        v.addWidget(s)
    return box


# ===========================================================================
# SettingsDialog
# ===========================================================================
SETTINGS_SECTIONS = [
    ("bot",     "Бот · Telegram",     "bot"),
    ("pocket",  "Pocket-нода",        "radio"),
    ("device",  "Устройство",         "usb"),
    ("limits",  "Лимиты",             "sliders"),
    ("gps",     "GPS β",              "gps"),
    ("sos",     "SOS",                "alert"),
    ("cats",    "Категории",          "cat"),
    ("wl",      "Whitelist",          "shield"),
]

# Catalog of supported hardware models — see relay/devices/__init__.py
import devices as _devices
NODE_MODELS = [(mid, label) for mid, label, _svg in _devices.NODE_CATALOG]


class SettingsDialog(QDialog):
    """Settings editor with sidebar navigation."""

    def __init__(self, parent: Optional[QWidget] = None,
                 open_section: str = "bot") -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки — relay/.env")
        self.resize(880, 580)
        self._data = settings_mod.load()
        self._touched = False
        self._build_ui()
        self._populate()
        self._select_section(open_section)

    # ------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setIconSize(QSize(14, 14))
        self.sidebar.setStyleSheet(
            f"QListWidget {{ background: {PALETTE['bg2']}; "
            f"border-right: 1px solid {PALETTE['hl1']}; padding: 8px 4px; }}"
            "QListWidget::item { padding: 6px 8px; margin: 1px 0; border-radius: 3px; }"
            f"QListWidget::item:selected {{ background: {PALETTE['accent_soft']}; "
            f"color: {PALETTE['t1']}; border-left: 2px solid {PALETTE['accent']}; }}"
        )
        for sid, label, ico in SETTINGS_SECTIONS:
            item = QListWidgetItem(make_icon(ico, color=PALETTE['t3']), "  " + label)
            item.setData(Qt.ItemDataRole.UserRole, sid)
            self.sidebar.addItem(item)
        self.sidebar.currentRowChanged.connect(self._on_sidebar)
        body.addWidget(self.sidebar)

        # Stack
        self.stack = QStackedWidget()
        self.stack.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.stack, 1)

        # Build sections
        self._sec_widgets: dict[str, QWidget] = {}
        self._sec_widgets["bot"] = self._build_bot()
        self._sec_widgets["pocket"] = self._build_pocket()
        self._sec_widgets["device"] = self._build_device()
        self._sec_widgets["limits"] = self._build_limits()
        self._sec_widgets["gps"] = self._build_gps()
        self._sec_widgets["sos"] = self._build_sos()
        self._sec_widgets["cats"] = self._build_cats()
        self._sec_widgets["wl"] = self._build_whitelist()
        for sid, _l, _i in SETTINGS_SECTIONS:
            self.stack.addWidget(self._sec_widgets[sid])

        root.addLayout(body, 1)

        # Footer
        foot = QFrame()
        foot.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-top: 1px solid {PALETTE['hl1']}; }}"
        )
        f = QHBoxLayout(foot)
        f.setContentsMargins(14, 10, 14, 10)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        f.addWidget(self._status_lbl, 1)
        cancel = QPushButton("Отмена")
        cancel.setProperty("role", "ghost")
        cancel.clicked.connect(self.reject)
        f.addWidget(cancel)
        save = ToolBtn("check", "Сохранить", role="primary")
        save.clicked.connect(self._save)
        f.addWidget(save)
        root.addWidget(foot)

    def _on_sidebar(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)

    def _select_section(self, sid: str) -> None:
        for i, (s, _l, _i) in enumerate(SETTINGS_SECTIONS):
            if s == sid:
                self.sidebar.setCurrentRow(i)
                self.stack.setCurrentIndex(i)
                return
        self.sidebar.setCurrentRow(0)
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------------ sections
    def _section_wrap(self, content: QWidget) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(14)
        v.addWidget(content)
        v.addStretch(1)
        return w

    def _build_bot(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("Telegram-бот",
                             "Токен от @BotFather и владелец (admin)"))

        gb = QGroupBox("ПОДКЛЮЧЕНИЕ")
        f = QFormLayout(gb)
        f.setVerticalSpacing(8)
        f.setHorizontalSpacing(12)

        self.ed_token = QLineEdit()
        self.ed_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_token.textChanged.connect(self._mark_touched)
        token_row = QHBoxLayout()
        token_row.addWidget(self.ed_token, 1)
        eye = QPushButton()
        eye.setIcon(make_icon("eyeOff", color=PALETTE["t3"]))
        eye.setIconSize(QSize(14, 14))
        eye.setFixedWidth(28)
        eye.setProperty("role", "ghost")
        def _toggle():
            shown = self.ed_token.echoMode() == QLineEdit.EchoMode.Normal
            self.ed_token.setEchoMode(
                QLineEdit.EchoMode.Password if shown else QLineEdit.EchoMode.Normal
            )
            eye.setIcon(make_icon("eye" if shown else "eyeOff", color=PALETTE["t3"]))
        eye.clicked.connect(_toggle)
        token_row.addWidget(eye)
        token_w = QWidget()
        token_w.setLayout(token_row)
        f.addRow("Токен бота:", token_w)
        f.addRow("", _hint(
            "Создай бота: @BotFather → /newbot → токен сюда. "
            "Формат NNNNN:XXXX..."
        ))

        self.ed_owner = QLineEdit()
        self.ed_owner.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{1,20}")))
        self.ed_owner.textChanged.connect(self._mark_touched)
        f.addRow("OWNER_ID:", self.ed_owner)
        f.addRow("", _hint(
            "Узнать свой numeric Telegram ID — через @my_id_bot. "
            "Скопируй число."
        ))

        v.addWidget(gb)

        # Display name shown to public users
        gb_dn = QGroupBox("ИМЯ ПОЛУЧАТЕЛЯ")
        f_dn = QFormLayout(gb_dn)
        f_dn.setVerticalSpacing(8)
        self.ed_display_name = QLineEdit()
        self.ed_display_name.setPlaceholderText("Михаил")
        self.ed_display_name.setMaxLength(30)
        self.ed_display_name.textChanged.connect(self._mark_touched)
        f_dn.addRow("Имя:", self.ed_display_name)
        f_dn.addRow("", _hint(
            "Это имя видят пользователи бота: «📨 Передаю сообщение для …»,"
            " «📍 Где …», «✓ Доставлено: …». По умолчанию «Михаил» — поменяй,"
            " если бот для другого человека."
        ))
        v.addWidget(gb_dn)

        return self._section_wrap(box)

    def _build_pocket(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("Карманная нода",
                             "ID устройства Михаила, куда уходят DM"))

        gb = QGroupBox("ИДЕНТИФИКАТОР")
        f = QFormLayout(gb)
        f.setVerticalSpacing(8)

        self.ed_pocket = QLineEdit()
        self.ed_pocket.setPlaceholderText("!1ba6795c")
        self.ed_pocket.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"!?[0-9a-fA-F]{0,8}"))
        )
        self.ed_pocket.textChanged.connect(self._mark_touched)
        f.addRow("ID карманной ноды:", self.ed_pocket)
        f.addRow("", _hint(
            "Формат !xxxxxxxx (8 hex-знаков). Посмотри в Meshtastic-приложении "
            "на карманном устройстве, либо через /nodes у запущенного бота."
        ))
        v.addWidget(gb)
        return self._section_wrap(box)

    def _build_device(self) -> QWidget:
        """Manual device model selector with SVG preview."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading(
            "Домашнее устройство",
            "Какая железка подключена по USB. Определить автоматически "
            "надёжно нельзя — выбери вручную."
        ))

        gb = QGroupBox("МОДЕЛЬ НОДЫ")
        gv = QVBoxLayout(gb)
        gv.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("Устройство:"))
        self.cb_node_model = QComboBox()
        for mid, label in NODE_MODELS:
            self.cb_node_model.addItem(label, mid)
        self.cb_node_model.currentIndexChanged.connect(self._mark_touched)
        self.cb_node_model.currentIndexChanged.connect(self._update_device_preview)
        row.addWidget(self.cb_node_model, 1)
        gv.addLayout(row)

        # SVG preview (centered, fixed-size frame)
        preview_frame = QFrame()
        preview_frame.setStyleSheet(
            "QFrame { background: #161a1f; "
            f"border: 1px solid {PALETTE['hl1']}; "
            "border-radius: 4px; }"
        )
        pf = QHBoxLayout(preview_frame)
        pf.setContentsMargins(10, 10, 10, 10)
        pf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_device_preview = QLabel()
        self.lbl_device_preview.setFixedSize(360, 220)
        self.lbl_device_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_device_preview.setStyleSheet(f"color: {PALETTE['t3']};")
        pf.addWidget(self.lbl_device_preview)
        gv.addWidget(preview_frame)

        gv.addWidget(_hint(
            "Используется для подсказок и (в будущем) команд управления "
            "мощностью LoRa, ролью узла, регионом, рестартом. Если своей "
            "модели не нашёл — выбери «Другая модель»."
        ))
        v.addWidget(gb)

        # Future: commands area
        gb2 = QGroupBox("КОМАНДЫ УСТРОЙСТВА")
        v2 = QVBoxLayout(gb2)
        coming = QLabel(
            "Скоро: повышение/понижение мощности LoRa, переключение роли "
            "(client / router), смена региона/канала, рестарт — прямо отсюда. "
            "Пока используй официальное приложение Meshtastic."
        )
        coming.setWordWrap(True)
        coming.setStyleSheet(
            f"color: {PALETTE['t3']}; font-size: 11px; line-height: 140%; "
            "padding: 4px 0;"
        )
        v2.addWidget(coming)
        v.addWidget(gb2)

        return self._section_wrap(box)

    def _update_device_preview(self) -> None:
        if not hasattr(self, "lbl_device_preview"):
            return
        model_id = self.cb_node_model.currentData() or "generic"
        svg_path = _devices.get_svg_path(model_id)
        if svg_path is None:
            self.lbl_device_preview.setPixmap(QPixmap())
            self.lbl_device_preview.setText(
                "—\n(нет картинки для этой модели)"
            )
            return
        try:
            from widgets import render_svg_to_pixmap
            self.lbl_device_preview.setPixmap(
                render_svg_to_pixmap(svg_path, self.lbl_device_preview.size())
            )
            self.lbl_device_preview.setText("")
        except Exception:
            self.lbl_device_preview.setText("(не удалось загрузить SVG)")

    def _build_limits(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("Лимиты", "Длина сообщений, TTL слотов, частота повторов"))

        gb1 = QGroupBox("СООБЩЕНИЯ И СЛОТЫ")
        f1 = QFormLayout(gb1)
        f1.setVerticalSpacing(8)
        self.sp_max_text = self._spin(20, 230)
        self.sp_slot_ttl = self._spin(1, 168)
        self.sp_slot_sticky = self._spin(1, 168)
        self.sp_user_pref = self._spin(3, 30)
        f1.addRow("Лимит символов в сообщении:", self.sp_max_text)
        f1.addRow("TTL слота (до ответа), ч:", self.sp_slot_ttl)
        f1.addRow("Sticky TTL (после ответа), ч:", self.sp_slot_sticky)
        f1.addRow("Длина username в префиксе:", self.sp_user_pref)
        v.addWidget(gb1)

        gb2 = QGroupBox("СВЯЗЬ С КАРМАНОМ")
        f2 = QFormLayout(gb2)
        self.sp_pocket_fresh = self._spin(1, 60)
        self.sp_pocket_stale = self._spin(2, 1440)
        f2.addRow("Pocket свежий ≤, мин:", self.sp_pocket_fresh)
        f2.addRow("Pocket устаревший ≤, мин:", self.sp_pocket_stale)
        v.addWidget(gb2)

        gb3 = QGroupBox("ПОВТОРНЫЕ ОТПРАВКИ")
        f3 = QFormLayout(gb3)
        self.sp_retry_init = self._spin(1, 60)
        self.sp_retry_max = self._spin(1, 240)
        f3.addRow("Первая пауза, мин:", self.sp_retry_init)
        f3.addRow("Максимум пауза, мин:", self.sp_retry_max)
        v.addWidget(gb3)

        return self._section_wrap(box)

    def _build_gps(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("GPS · бета",
                             "Передача координат карманной ноды (POSITION_APP)"))

        warn = QFrame()
        warn.setStyleSheet(
            "QFrame { background: rgba(240,181,65,0.08); "
            "border: 1px solid rgba(240,181,65,0.25); "
            "border-radius: 3px; padding: 8px 10px; }"
        )
        wl = QHBoxLayout(warn)
        wl.setContentsMargins(8, 6, 8, 6)
        wic = QLabel()
        wic.setPixmap(make_icon("alert", color=PALETTE["warn"], size=16).pixmap(16, 16))
        wl.addWidget(wic)
        wlbl = QLabel(
            "Бета. Функция не тестировалась автором — нет физического GPS-модуля. "
            "Включай только если уверен."
        )
        wlbl.setWordWrap(True)
        wlbl.setStyleSheet(f"color: {PALETTE['warn']}; font-size: 11px;")
        wl.addWidget(wlbl, 1)
        v.addWidget(warn)

        self.cb_gps = QCheckBox("Включить GPS-функции (/where, координаты в SOS)")
        self.cb_gps.toggled.connect(self._mark_touched)
        v.addWidget(self.cb_gps)

        gb = QGroupBox("ПОРОГИ И ЛИМИТЫ")
        f = QFormLayout(gb)
        self.sp_gps_fresh = self._spin(1, 60)
        self.sp_gps_stale = self._spin(1, 240)
        self.sp_gps_max = self._spin(1, 1440)
        self.sp_where_rl = self._spin(0, 60)
        f.addRow("Свежий фикс ≤, мин:", self.sp_gps_fresh)
        f.addRow("Устаревший фикс ≤, мин:", self.sp_gps_stale)
        f.addRow("Максимум возраст фикса, мин:", self.sp_gps_max)
        f.addRow("Rate limit /where, мин:", self.sp_where_rl)
        v.addWidget(gb)
        return self._section_wrap(box)

    def _build_sos(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("SOS · тревога",
                             "Триггер: «#SOS текст» с карманной ноды"))

        self.cb_sos = QCheckBox("Включить SOS")
        self.cb_sos.toggled.connect(self._mark_touched)
        v.addWidget(self.cb_sos)

        gb1 = QGroupBox("СООБЩЕНИЕ")
        f1 = QVBoxLayout(gb1)
        self.te_sos_msg = QPlainTextEdit()
        self.te_sos_msg.setMaximumHeight(80)
        self.te_sos_msg.textChanged.connect(self._mark_touched)
        f1.addWidget(self.te_sos_msg)
        self.cb_sos_coords = QCheckBox("Присылать координаты карманной ноды (если GPS работает)")
        self.cb_sos_coords.toggled.connect(self._mark_touched)
        f1.addWidget(self.cb_sos_coords)
        v.addWidget(gb1)

        gb2 = QGroupBox("ПОЛУЧАТЕЛИ")
        f2 = QVBoxLayout(gb2)
        self.lst_sos = QListWidget()
        self.lst_sos.setMaximumHeight(140)
        f2.addWidget(self.lst_sos)
        row = QHBoxLayout()
        b1 = ToolBtn("users", "Из юзеров…")
        b1.clicked.connect(self._sos_from_users)
        row.addWidget(b1)
        b2 = ToolBtn("plus", "ID вручную")
        b2.clicked.connect(self._sos_manual)
        row.addWidget(b2)
        b3 = ToolBtn("trash", "Удалить")
        b3.setProperty("role", "ghost")
        b3.clicked.connect(self._sos_remove)
        row.addWidget(b3)
        row.addStretch(1)
        f2.addLayout(row)
        v.addWidget(gb2)
        return self._section_wrap(box)

    def _build_cats(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(10)
        v.addWidget(_heading("Категории",
                             "Метки для разных аудиторий + готовые ссылки"))

        # Explainer card
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: rgba(106,161,255,0.06); "
            "border: 1px solid rgba(106,161,255,0.20); "
            "border-radius: 4px; padding: 10px 12px; }"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        what = QLabel("<b>Что это</b>")
        what.setStyleSheet(f"color: {PALETTE['t1']};")
        cl.addWidget(what)
        cl.addWidget(_hint(
            "Каждая категория = пара «название + тег». Тег превращается "
            "в готовую ссылку <code>t.me/твой_бот?start=&lt;тег&gt;</code>."
        ))

        why = QLabel("<b>Зачем</b>")
        why.setStyleSheet(f"color: {PALETTE['t1']};")
        cl.addWidget(why)
        cl.addWidget(_hint(
            "Раздаёшь разным аудиториям свои ссылки — коллегам одну, "
            "друзьям другую. Каждый, кто пришёл по своей ссылке, получает "
            "метку категории. У тебя в кармане сразу видно, «откуда» "
            "сообщение: префикс выглядит так — "
            "<code>[@3 work:maria 16:15] заказ готов?</code>"
        ))

        how = QLabel("<b>Как использовать</b>")
        how.setStyleSheet(f"color: {PALETTE['t1']};")
        cl.addWidget(how)
        cl.addWidget(_hint(
            "Создай категорию ниже → ссылку для копирования получишь "
            "командой <code>/link</code> в чате с ботом → раздай нужным "
            "людям. Без категорий бот тоже работает — просто без меток."
        ))
        v.addWidget(card)

        self.cat_list = QListWidget()
        v.addWidget(self.cat_list, 1)

        row = QHBoxLayout()
        ba = ToolBtn("plus", "Добавить")
        ba.clicked.connect(self._cat_add)
        br = ToolBtn("trash", "Удалить")
        br.setProperty("role", "ghost")
        br.clicked.connect(self._cat_remove)
        bf = ToolBtn("refresh", "Обновить")
        bf.setProperty("role", "ghost")
        bf.clicked.connect(self._cat_refresh)
        row.addWidget(ba)
        row.addWidget(br)
        row.addWidget(bf)
        row.addStretch(1)
        v.addLayout(row)

        self._cat_refresh()
        return self._section_wrap(box)

    def _build_whitelist(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setSpacing(12)
        v.addWidget(_heading("Whitelist · закрытый режим",
                             "Кому разрешено писать боту"))

        self.cb_wl = QCheckBox("Закрытый режим (whitelist)")
        self.cb_wl.toggled.connect(self._mark_touched)
        v.addWidget(self.cb_wl)
        v.addWidget(_hint(
            "Если включено — бот принимает сообщения только от пользователей с "
            "пометкой WL. Управление списком — окно «Пользователи» (меню «Сервис»)."
        ))
        return self._section_wrap(box)

    def _spin(self, lo: int, hi: int) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.valueChanged.connect(self._mark_touched)
        return s

    # ------------------------------------------------------------ data <-> UI
    def _populate(self) -> None:
        s = self._data
        self.ed_token.setText(s.get("bot_token") or "")
        self.ed_owner.setText(str(s.get("owner_id") or ""))
        self.ed_display_name.setText(s.get("display_name") or "Михаил")
        self.ed_pocket.setText(s.get("pocket_node_id") or "")
        # Device model
        target_model = (s.get("node_model") or "generic")
        for i in range(self.cb_node_model.count()):
            if self.cb_node_model.itemData(i) == target_model:
                self.cb_node_model.setCurrentIndex(i)
                break
        self._update_device_preview()
        self.cb_wl.setChecked(bool(s.get("whitelist_enabled")))
        self.cb_gps.setChecked(bool(s.get("gps_enabled")))
        self.sp_gps_fresh.setValue(int(s.get("gps_fix_fresh_min") or 5))
        self.sp_gps_stale.setValue(int(s.get("gps_fix_stale_min") or 30))
        self.sp_gps_max.setValue(int(s.get("gps_fix_max_min") or 120))
        self.sp_where_rl.setValue(int(s.get("where_rate_limit_min") or 5))
        self.cb_sos.setChecked(bool(s.get("sos_enabled")))
        self.te_sos_msg.setPlainText(s.get("sos_message") or "")
        self.cb_sos_coords.setChecked(bool(s.get("sos_include_coords", True)))
        for tg_id in (s.get("sos_recipients") or []):
            self._sos_append(int(tg_id))
        self.sp_max_text.setValue(int(s.get("max_text_length") or 170))
        self.sp_slot_ttl.setValue(int(s.get("slot_ttl_hours") or 20))
        self.sp_slot_sticky.setValue(int(s.get("slot_sticky_hours") or 10))
        self.sp_user_pref.setValue(int(s.get("max_username_in_prefix") or 10))
        self.sp_pocket_fresh.setValue(int(s.get("pocket_fresh_min") or 10))
        self.sp_pocket_stale.setValue(int(s.get("pocket_stale_min") or 60))
        self.sp_retry_init.setValue(int(s.get("retry_initial_delay_min") or 2))
        self.sp_retry_max.setValue(int(s.get("retry_max_interval_min") or 15))
        self._touched = False
        self._update_status()

    def _collect(self) -> dict:
        recips = [
            int(self.lst_sos.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.lst_sos.count())
        ]
        return {
            "bot_token":              self.ed_token.text().strip(),
            "owner_id":               int(self.ed_owner.text() or 0),
            "pocket_node_id":         self.ed_pocket.text().strip(),
            "last_com_port":          self._data.get("last_com_port", ""),
            "display_name":           self.ed_display_name.text().strip() or "Михаил",
            "node_model":             self.cb_node_model.currentData() or "generic",
            "max_text_length":        self.sp_max_text.value(),
            "slot_ttl_hours":         self.sp_slot_ttl.value(),
            "slot_sticky_hours":      self.sp_slot_sticky.value(),
            "max_username_in_prefix": self.sp_user_pref.value(),
            "pocket_fresh_min":       self.sp_pocket_fresh.value(),
            "pocket_stale_min":       self.sp_pocket_stale.value(),
            "gps_enabled":            self.cb_gps.isChecked(),
            "gps_fix_fresh_min":      self.sp_gps_fresh.value(),
            "gps_fix_stale_min":      self.sp_gps_stale.value(),
            "gps_fix_max_min":        self.sp_gps_max.value(),
            "where_rate_limit_min":   self.sp_where_rl.value(),
            "whitelist_enabled":      self.cb_wl.isChecked(),
            "sos_enabled":            self.cb_sos.isChecked(),
            "sos_recipients":         recips,
            "sos_message":            self.te_sos_msg.toPlainText().strip(),
            "sos_include_coords":     self.cb_sos_coords.isChecked(),
            "retry_initial_delay_min": self.sp_retry_init.value(),
            "retry_max_interval_min": self.sp_retry_max.value(),
        }

    def _save(self) -> None:
        data = self._collect()
        errs = settings_mod.validate(data)
        if errs:
            QMessageBox.warning(
                self, "Не сохранено — ошибки:",
                "\n".join("• " + e for e in errs),
            )
            return
        try:
            settings_mod.save(data)
        except OSError as e:
            QMessageBox.critical(self, "Ошибка записи", f"Не удалось:\n{e}")
            return
        self._touched = False
        QMessageBox.information(
            self, "Сохранено",
            "Настройки сохранены в .env.\n"
            "Если релей запущен — перезапусти, чтобы применилось.",
        )
        self.accept()

    def _mark_touched(self, *_) -> None:
        self._touched = True
        self._update_status()

    def _update_status(self) -> None:
        if self._touched:
            self._status_lbl.setText("● несохранённые изменения")
            self._status_lbl.setStyleSheet(
                f"color: {PALETTE['warn']}; font-family: 'Consolas', monospace; "
                "font-size: 11px;"
            )
        else:
            self._status_lbl.setText("сохранено")
            self._status_lbl.setStyleSheet(
                f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; "
                "font-size: 11px;"
            )

    # ------------------------------------------------------------ SOS edits
    def _sos_append(self, tg_id: int) -> None:
        for i in range(self.lst_sos.count()):
            if int(self.lst_sos.item(i).data(Qt.ItemDataRole.UserRole)) == tg_id:
                return
        users_by_id = {u["tg_user_id"]: u for u in db.list_users()}
        u = users_by_id.get(tg_id)
        name = (u.get("tg_username") or u.get("first_name") if u else None) or "(нет в базе)"
        item = QListWidgetItem(f"{tg_id} — {name}")
        item.setData(Qt.ItemDataRole.UserRole, tg_id)
        item.setIcon(make_icon("user", color=PALETTE["t3"]))
        self.lst_sos.addItem(item)
        self._mark_touched()

    def _sos_from_users(self) -> None:
        users = db.list_users()
        if not users:
            QMessageBox.information(
                self, "Пусто",
                "В базе ещё нет пользователей. Добавь вручную или дождись первых сообщений.",
            )
            return
        items = [
            f"{u['tg_user_id']} — {u.get('tg_username') or u.get('first_name') or '?'}"
            for u in users
        ]
        choice, ok = QInputDialog.getItem(
            self, "Получатель SOS", "Выбери пользователя:", items, 0, False
        )
        if not ok or not choice:
            return
        self._sos_append(int(choice.split(" — ", 1)[0]))

    def _sos_manual(self) -> None:
        text, ok = QInputDialog.getText(
            self, "ID вручную",
            "Telegram numeric ID получателя (узнать через @my_id_bot):",
        )
        if not ok or not text.strip():
            return
        try:
            self._sos_append(int(text.strip()))
        except ValueError:
            QMessageBox.warning(self, "Не число", "Ожидал numeric ID.")

    def _sos_remove(self) -> None:
        for item in self.lst_sos.selectedItems():
            self.lst_sos.takeItem(self.lst_sos.row(item))
        self._mark_touched()

    # ------------------------------------------------------------ Categories edits
    def _cat_refresh(self) -> None:
        self.cat_list.clear()
        for c in db.list_categories():
            item = QListWidgetItem(f"{c['name']}    ·    tag: {c['tag']}")
            item.setData(Qt.ItemDataRole.UserRole, c['tag'])
            item.setIcon(make_icon("link", color=PALETTE["info"]))
            self.cat_list.addItem(item)

    def _cat_add(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая категория", "Название:")
        if not ok or not name.strip():
            return
        tag, ok = QInputDialog.getText(
            self, "Тег ссылки",
            "Тег (латиница/цифры/_, пойдёт в t.me/bot?start=<тег>):",
        )
        if not ok or not tag.strip():
            return
        tag = tag.strip().lower()
        if not all(c.isalnum() or c == "_" for c in tag):
            QMessageBox.warning(self, "Плохой тег", "Только латиница/цифры/_.")
            return
        if not db.add_category(name, tag):
            QMessageBox.warning(self, "Занято", f"Тег '{tag}' уже используется.")
            return
        self._cat_refresh()

    def _cat_remove(self) -> None:
        item = self.cat_list.currentItem()
        if item is None:
            return
        tag = item.data(Qt.ItemDataRole.UserRole)
        ok = QMessageBox.question(
            self, "Удалить?",
            f"Удалить категорию с тегом '{tag}'?\nСсылки с этим тегом перестанут работать.",
        ) == QMessageBox.StandardButton.Yes
        if not ok:
            return
        db.remove_category(tag)
        self._cat_refresh()


# ===========================================================================
# UsersDialog
# ===========================================================================
class UsersDialog(QDialog):
    """Top filter pills + search + table of all known users."""

    COL_NAME, COL_TG, COL_CAT, COL_WL, COL_FAV, COL_BAN, COL_LAST = range(7)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Пользователи · relay.db")
        self.resize(940, 580)
        self._filter = "all"
        self._query = ""
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Filters bar
        filt = QFrame()
        filt.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-bottom: 1px solid {PALETTE['hl1']}; }}"
        )
        fl = QHBoxLayout(filt)
        fl.setContentsMargins(10, 8, 10, 8)
        fl.setSpacing(8)
        self._filter_btns: dict[str, QPushButton] = {}
        for fid, label, ico in [
            ("all", "Все", "users"),
            ("wl",  "Whitelist", "shield"),
            ("fav", "Избранные", "star"),
            ("ban", "Бан", "ban"),
        ]:
            btn = ToolBtn(ico, label)
            btn.setCheckable(True)
            btn.setProperty("role", "ghost")
            btn.clicked.connect(lambda _, x=fid: self._set_filter(x))
            fl.addWidget(btn)
            self._filter_btns[fid] = btn
        self._filter_btns["all"].setChecked(True)
        self._filter_btns["all"].setProperty("role", "primary")
        fl.addWidget(ToolSep())

        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("поиск по имени, @, ID…")
        self.ed_search.textChanged.connect(self._on_search)
        self.ed_search.setMaximumWidth(280)
        fl.addWidget(self.ed_search, 1)

        fl.addStretch(1)
        bp = ToolBtn("plus", "Добавить вручную")
        bp.clicked.connect(self._add_manual)
        fl.addWidget(bp)
        bre = ToolBtn("refresh", "Обновить")
        bre.setProperty("role", "ghost")
        bre.clicked.connect(self._refresh)
        fl.addWidget(bre)
        root.addWidget(filt)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Пользователь",
            "TG ID",
            "Категория",
            "Белый список",
            "Избранный",
            "Бан",
            "Последняя активность",
        ])
        h = self.table.horizontalHeader()
        # Name and TG-id are content-sized; flag columns get fixed width
        # so labels don't wrap; last col stretches to fill the rest.
        h.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(self.COL_TG, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(self.COL_CAT, QHeaderView.ResizeMode.ResizeToContents)
        for c in (self.COL_WL, self.COL_FAV, self.COL_BAN):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(self.COL_LAST, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(self.COL_NAME, 200)
        self.table.setColumnWidth(self.COL_WL, 110)
        self.table.setColumnWidth(self.COL_FAV, 100)
        self.table.setColumnWidth(self.COL_BAN, 80)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        # Footer
        foot = QFrame()
        foot.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-top: 1px solid {PALETTE['hl1']}; }}"
        )
        fa = QHBoxLayout(foot)
        fa.setContentsMargins(14, 10, 14, 10)
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        fa.addWidget(self._count_lbl, 1)
        bc = QPushButton("Закрыть")
        bc.setProperty("role", "ghost")
        bc.clicked.connect(self.accept)
        fa.addWidget(bc)
        root.addWidget(foot)

    def _set_filter(self, fid: str) -> None:
        self._filter = fid
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == fid)
            btn.setProperty("role", "primary" if k == fid else "ghost")
            btn.style().unpolish(btn); btn.style().polish(btn)
        self._refresh()

    def _on_search(self, text: str) -> None:
        self._query = text.lower()
        self._refresh()

    def _refresh(self) -> None:
        users = db.list_users()
        # filter
        def matches(u: dict) -> bool:
            if self._filter == "wl"  and not u.get("whitelisted"): return False
            if self._filter == "fav" and not u.get("is_fav"):       return False
            if self._filter == "ban" and not u.get("banned"):       return False
            if self._query:
                blob = " ".join([
                    str(u.get("tg_user_id", "")),
                    u.get("tg_username") or "",
                    u.get("first_name") or "",
                ]).lower()
                if self._query not in blob:
                    return False
            return True

        rows = [u for u in users if matches(u)]
        self.table.setRowCount(len(rows))
        for r, u in enumerate(rows):
            self._fill_row(r, u)
        self._count_lbl.setText(f"показано {len(rows)} / {len(users)}")

    def _fill_row(self, r: int, u: dict) -> None:
        tg_id = u["tg_user_id"]
        name = u.get("first_name") or "—"
        uname = u.get("tg_username") or ""
        last = datetime.fromtimestamp(u["last_seen"]).strftime("%Y-%m-%d %H:%M")
        cat = u.get("entry_tag") or ""

        # Name cell — two-line
        nm = QTableWidgetItem()
        nm.setData(Qt.ItemDataRole.UserRole, tg_id)
        nm.setText(f"{name}\n@{uname}" if uname else name)
        nm.setForeground(QColor(PALETTE["t1"] if not u.get("banned") else PALETTE["t3"]))
        self.table.setItem(r, self.COL_NAME, nm)

        tg = QTableWidgetItem(str(tg_id))
        tg.setFont(QFont("Consolas", 9))
        tg.setForeground(QColor(PALETTE["t2"]))
        self.table.setItem(r, self.COL_TG, tg)

        if cat:
            cat_w = Badge("cat", text=cat)
            wrap = QWidget(); wl = QHBoxLayout(wrap); wl.setContentsMargins(8, 0, 8, 0); wl.addWidget(cat_w); wl.addStretch(1)
            self.table.setCellWidget(r, self.COL_CAT, wrap)
        else:
            self.table.setItem(r, self.COL_CAT, QTableWidgetItem("—"))

        # checkboxes for WL/FAV/BAN
        self._set_check(r, self.COL_WL, bool(u.get("whitelisted")),
                        lambda v, tid=tg_id: db.set_flag(tid, "whitelisted", v))
        self._set_check(r, self.COL_FAV, bool(u.get("is_fav")),
                        lambda v, tid=tg_id: db.set_fav(tid, v))
        self._set_check(r, self.COL_BAN, bool(u.get("banned")),
                        lambda v, tid=tg_id: db.set_flag(tid, "banned", v))

        last_w = QTableWidgetItem(last)
        last_w.setForeground(QColor(PALETTE["t3"]))
        self.table.setItem(r, self.COL_LAST, last_w)

    def _set_check(self, row: int, col: int, checked: bool, on_toggle) -> None:
        cb = QCheckBox()
        cb.setChecked(checked)
        cb.toggled.connect(on_toggle)
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(cb)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setCellWidget(row, col, wrap)

    def _add_manual(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Добавить пользователя",
            "Telegram numeric ID (узнать через @my_id_bot):",
        )
        if not ok or not text.strip():
            return
        try:
            tg_id = int(text.strip())
        except ValueError:
            QMessageBox.warning(self, "Не число", "Ожидал numeric ID.")
            return
        name, ok2 = QInputDialog.getText(self, "Имя", "Имя/заметка (необязательно):")
        db.ensure_user(tg_id, name.strip() if (ok2 and name.strip()) else None)
        self._refresh()


# ===========================================================================
# SlotsDialog — read-only view of active @N slots
# ===========================================================================
class SlotsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Активные слоты @N")
        self.resize(820, 500)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame()
        head.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-bottom: 1px solid {PALETTE['hl1']}; }}"
        )
        hl = QHBoxLayout(head)
        hl.setContentsMargins(10, 8, 10, 8)
        self._info = QLabel("")
        self._info.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        hl.addWidget(self._info, 1)
        bre = ToolBtn("refresh", "Обновить")
        bre.setProperty("role", "ghost")
        bre.clicked.connect(self._refresh)
        hl.addWidget(bre)
        root.addWidget(head)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Слот", "Пользователь", "Сообщение", "Закреплён", "Прогресс", "Истекает через"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(3, 96)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 130)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        foot = QFrame()
        foot.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-top: 1px solid {PALETTE['hl1']}; }}"
        )
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.addStretch(1)
        bc = QPushButton("Закрыть")
        bc.setProperty("role", "ghost")
        bc.clicked.connect(self.accept)
        fl.addWidget(bc)
        root.addWidget(foot)

    def _refresh(self) -> None:
        slots = db.list_active_slots()
        self.table.setRowCount(len(slots))
        now = int(time.time())
        for r, s in enumerate(slots):
            slot_n = s["slot_n"]
            name = s.get("tg_username") or s.get("first_name") or str(s["tg_user_id"])
            tag = s.get("entry_tag")
            label = f"{tag}:{name}" if tag else name
            sticky = bool(s.get("was_replied"))
            last_msg = (s.get("last_message") or "").strip() or "—"
            remaining = max(0, s["expires_at"] - now)
            total = s["expires_at"] - s["created_at"] or remaining
            pct = int(100 * remaining / total) if total > 0 else 0
            hh = remaining // 3600
            mm = (remaining % 3600) // 60

            # @N
            slot_w = QTableWidgetItem(f"@{slot_n}")
            slot_w.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            slot_w.setForeground(QColor(PALETTE["accent"]))
            slot_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, slot_w)

            # Пользователь
            name_w = QTableWidgetItem(label)
            name_w.setFont(QFont("Consolas", 9))
            self.table.setItem(r, 1, name_w)

            # Сообщение (last_message, italic)
            msg_w = QTableWidgetItem(last_msg)
            msg_w.setForeground(QColor(PALETTE["t2"]))
            f = QFont(); f.setItalic(True); f.setPointSize(10)
            msg_w.setFont(f)
            msg_w.setToolTip(last_msg)
            self.table.setItem(r, 2, msg_w)

            # Закреплён ★
            sticky_w = QTableWidgetItem("★ да" if sticky else "—")
            sticky_w.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sticky_w.setForeground(QColor(PALETTE["warn"] if sticky else PALETTE["t4"]))
            f = QFont()
            if sticky:
                f.setBold(True)
            sticky_w.setFont(f)
            self.table.setItem(r, 3, sticky_w)

            # Прогресс
            prog = QProgressBar()
            prog.setTextVisible(False)
            prog.setRange(0, 100)
            prog.setValue(pct)
            prog.setFixedHeight(8)
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(8, 0, 8, 0)
            wl.addWidget(prog)
            self.table.setCellWidget(r, 4, wrap)

            # Истекает через
            tone = "err" if pct < 10 else "warn" if pct < 20 else "t2"
            time_w = QTableWidgetItem(f"{hh:02d}ч {mm:02d}мин")
            time_w.setFont(QFont("Consolas", 9))
            time_w.setForeground(QColor(PALETTE[tone]))
            self.table.setItem(r, 5, time_w)

            self.table.setRowHeight(r, 28)

        self._info.setText(
            f"всего активных слотов: {len(slots)} · обновляется вручную (нажми «Обновить»)"
        )


# ===========================================================================
# OnboardingDialog — first-run 3-step wizard
# ===========================================================================
class OnboardingDialog(QDialog):
    """4-step first-run wizard: language → token → owner ID → pocket node ID.

    Implementation note: использует QStackedWidget вместо удаления-пересоздания
    виджетов через deleteLater. Прежняя реализация падала на кнопке «Назад»
    из-за dangling Python-ссылок на уничтоженные C++ Qt-объекты.
    """

    STEP_LANG, STEP_TOKEN, STEP_OWNER, STEP_POCKET = 0, 1, 2, 3
    TOTAL_STEPS = 4

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Подгружаем текущий выбранный язык. На первом запуске — RU,
        # после клика на radio-кнопке language step _render обновит UI на лету.
        self._lang = settings_mod.load().get("gui_lang", "ru")
        self.setWindowTitle(_t("wizard.title", self._lang))
        self.resize(580, 480)
        self._step = self.STEP_LANG
        self._build_ui()
        self._render_chrome()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-bottom: 1px solid {PALETTE['hl1']}; }}"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 14, 20, 14)
        ic = QLabel()
        ic.setPixmap(make_icon("wand", color=PALETTE["accent"], size=20).pixmap(20, 20))
        hl.addWidget(ic)
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"color: {PALETTE['t1']}; font-size: 14px; font-weight: 600;"
        )
        hl.addWidget(self._title_lbl)
        hl.addStretch(1)
        self._step_lbl = QLabel("")
        self._step_lbl.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace;"
        )
        hl.addWidget(self._step_lbl)
        root.addWidget(hdr)

        # ── Body: QStackedWidget со страницами на все шаги ────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_page_lang())     # index 0
        self._stack.addWidget(self._build_page_token())    # index 1
        self._stack.addWidget(self._build_page_owner())    # index 2
        self._stack.addWidget(self._build_page_pocket())   # index 3
        root.addWidget(self._stack, 1)

        # ── Footer ────────────────────────────────────────────────────
        foot = QFrame()
        foot.setStyleSheet(
            f"QFrame {{ background: {PALETTE['bg2']}; "
            f"border-top: 1px solid {PALETTE['hl1']}; }}"
        )
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(14, 10, 14, 10)
        self.bskip = QPushButton()
        self.bskip.setProperty("role", "ghost")
        self.bskip.clicked.connect(self.reject)
        fl.addWidget(self.bskip)
        fl.addStretch(1)
        self.bback = ToolBtn("chevLeft", "")
        self.bback.setProperty("role", "ghost")
        self.bback.clicked.connect(self._back)
        fl.addWidget(self.bback)
        self.bnext = ToolBtn("chevRight", "")
        self.bnext.setProperty("role", "primary")
        self.bnext.clicked.connect(self._next)
        fl.addWidget(self.bnext)
        root.addWidget(foot)

    # ── Page builders (создаются один раз) ────────────────────────────

    def _build_page_lang(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self._lang_heading = _heading("", "")
        lay.addWidget(self._lang_heading)
        self._lang_hint = _hint("")
        lay.addWidget(self._lang_hint)

        self._rb_ru = QRadioButton()
        self._rb_en = QRadioButton()
        self._rb_ru.setChecked(self._lang == "ru")
        self._rb_en.setChecked(self._lang == "en")
        self._rb_ru.toggled.connect(lambda checked: self._on_lang_changed("ru") if checked else None)
        self._rb_en.toggled.connect(lambda checked: self._on_lang_changed("en") if checked else None)
        lay.addWidget(self._rb_ru)
        lay.addWidget(self._rb_en)
        lay.addStretch(1)
        return page

    def _build_page_token(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self._token_heading = _heading("", "")
        lay.addWidget(self._token_heading)
        self._token_hint = _hint("")
        lay.addWidget(self._token_hint)
        self.ed_token = QLineEdit()
        self.ed_token.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self.ed_token)
        lay.addStretch(1)
        return page

    def _build_page_owner(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self._owner_heading = _heading("", "")
        lay.addWidget(self._owner_heading)
        self._owner_hint = _hint("")
        lay.addWidget(self._owner_hint)
        self.ed_owner = QLineEdit()
        self.ed_owner.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{1,20}"))
        )
        lay.addWidget(self.ed_owner)
        lay.addStretch(1)
        return page

    def _build_page_pocket(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        self._pocket_heading = _heading("", "")
        lay.addWidget(self._pocket_heading)
        self._pocket_hint = _hint("")
        lay.addWidget(self._pocket_hint)
        self.ed_pocket = QLineEdit()
        self.ed_pocket.setPlaceholderText("!1ba6795c")
        self.ed_pocket.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"!?[0-9a-fA-F]{0,8}"))
        )
        lay.addWidget(self.ed_pocket)
        lay.addStretch(1)
        return page

    # ── Re-render texts based on _lang and _step ─────────────────────

    def _render_chrome(self) -> None:
        """Обновляет тексты заголовков/кнопок/страниц под текущий язык
        и активную страницу. Безопасен: только setText/setEnabled/setCurrentIndex,
        ничего не уничтожает."""
        L = self._lang
        self.setWindowTitle(_t("wizard.title", L))
        self._title_lbl.setText(_t("wizard.welcome", L))
        self._step_lbl.setText(
            _t("wizard.step_of", L).format(n=self._step + 1, total=self.TOTAL_STEPS)
        )

        # Page-level тексты — обновляем все, чтобы переключение языка
        # на странице 0 моментально применялось ко всем страницам.
        self._set_heading(self._lang_heading,
                          _t("wizard.step_lang.title", L),
                          _t("wizard.step_lang.hint", L))
        self._lang_hint.setText("")
        self._rb_ru.setText(_t("wizard.step_lang.option_ru", L))
        self._rb_en.setText(_t("wizard.step_lang.option_en", L))

        self._set_heading(self._token_heading,
                          _t("wizard.step_token.title", L),
                          _t("wizard.step_token.lede", L))
        self._token_hint.setText(_t("wizard.step_token.hint", L))

        self._set_heading(self._owner_heading,
                          _t("wizard.step_owner.title", L),
                          _t("wizard.step_owner.lede", L))
        self._owner_hint.setText(_t("wizard.step_owner.hint", L))

        self._set_heading(self._pocket_heading,
                          _t("wizard.step_pocket.title", L),
                          _t("wizard.step_pocket.lede", L))
        self._pocket_hint.setText(_t("wizard.step_pocket.hint", L))

        # Кнопки футера
        self.bskip.setText(_t("wizard.btn_skip", L))
        self.bback.setText("  " + _t("wizard.btn_back", L))
        is_last = self._step == self.STEP_POCKET
        self.bnext.setText("  " + _t("wizard.btn_done" if is_last else "wizard.btn_next", L))
        self.bback.setEnabled(self._step > 0)

        # Активная страница
        self._stack.setCurrentIndex(self._step)

    @staticmethod
    def _set_heading(heading_widget: QWidget, title: str, lede: str) -> None:
        """_heading() вернул composite-виджет (заголовок+подпись).
        Прокладываем тексты через первые два QLabel'а внутри."""
        labels = heading_widget.findChildren(QLabel)
        if len(labels) >= 1:
            labels[0].setText(title)
        if len(labels) >= 2:
            labels[1].setText(lede)

    # ── Event handlers ────────────────────────────────────────────────

    def _on_lang_changed(self, lang: str) -> None:
        if lang in ("ru", "en") and lang != self._lang:
            self._lang = lang
            self._render_chrome()

    def _next(self) -> None:
        L = self._lang
        if self._step == self.STEP_TOKEN and not self.ed_token.text().strip():
            QMessageBox.warning(self, _t("wizard.warn_need", L), _t("wizard.warn_token", L))
            return
        if self._step == self.STEP_OWNER:
            try:
                if int(self.ed_owner.text() or 0) <= 0:
                    raise ValueError()
            except ValueError:
                QMessageBox.warning(self, _t("wizard.warn_need", L), _t("wizard.warn_owner", L))
                return
        if self._step == self.STEP_POCKET:
            self._finish()
            return
        self._step += 1
        self._render_chrome()

    def _back(self) -> None:
        if self._step > 0:
            self._step -= 1
            self._render_chrome()

    def _finish(self) -> None:
        L = self._lang
        pid = self.ed_pocket.text().strip()
        if not (pid.startswith("!") and len(pid) == 9
                and all(c in "0123456789abcdefABCDEF" for c in pid[1:])):
            QMessageBox.warning(self, _t("wizard.warn_need", L),
                                _t("wizard.warn_pocket", L))
            return
        data = settings_mod.load()
        data["gui_lang"] = self._lang
        data["bot_token"] = self.ed_token.text().strip()
        data["owner_id"] = int(self.ed_owner.text() or 0)
        data["pocket_node_id"] = pid
        errs = settings_mod.validate(data)
        if errs:
            QMessageBox.warning(self, _t("wizard.warn_validation", L),
                                "\n".join("• " + e for e in errs))
            return
        try:
            settings_mod.save(data)
        except (OSError, PermissionError) as e:
            QMessageBox.critical(self, _t("wizard.warn_save", L), str(e))
            return
        self.accept()


# ===========================================================================
# AboutDialog
# ===========================================================================
class AboutDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("О программе")
        self.setFixedSize(420, 360)
        self._build_ui()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 14)
        v.setSpacing(14)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ic = QLabel()
        ic.setPixmap(make_icon("radio", color="#06121b", size=24).pixmap(48, 48))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setFixedSize(56, 56)
        ic.setStyleSheet(
            f"QLabel {{ background: {PALETTE['accent']}; border-radius: 8px; }}"
        )
        wrap = QHBoxLayout(); wrap.setAlignment(Qt.AlignmentFlag.AlignCenter); wrap.addWidget(ic)
        v.addLayout(wrap)

        title = QLabel("Meshgram Relay")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {PALETTE['t1']}; font-size: 16px; font-weight: 600;"
        )
        v.addWidget(title)

        sub = QLabel(f"v0.5 · Python {sys.version.split()[0]} · PyQt6")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; font-size: 11px;"
        )
        v.addWidget(sub)

        desc = QLabel(
            "Мост Telegram ↔ Meshtastic. Превращает обычный мессенджер в "
            "адресный канал к одному человеку, даже когда у него нет интернета."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {PALETTE['t2']}; font-size: 12px; line-height: 150%;"
        )
        v.addWidget(desc)

        site = QLabel('<a href="https://meshgram.site" '
                      f'style="color: {PALETTE["info"]}; text-decoration:none;">meshgram.site</a>')
        site.setAlignment(Qt.AlignmentFlag.AlignCenter)
        site.setOpenExternalLinks(True)
        site.setStyleSheet("font-size: 11px;")
        v.addWidget(site)

        v.addStretch(1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.button(QDialogButtonBox.StandardButton.Ok).setProperty("role", "primary")
        btns.accepted.connect(self.accept)
        v.addWidget(btns)
