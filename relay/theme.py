"""
Color palette + global QSS — ported from out_dis/app/styles.css.

Designer's CSS variables map to the PALETTE dict. The QSS string is templated
and uses these values verbatim. `apply_theme(app)` installs the QSS and a
matching QPalette so non-styled widgets blend in.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Palette (single source of truth; matches CSS :root vars)
# ---------------------------------------------------------------------------
PALETTE = {
    # Backgrounds
    "bg0":      "#0f1216",
    "bg1":      "#1c2026",
    "bg2":      "#232830",
    "bg3":      "#2a3038",
    "bg4":      "#323943",
    "bg5":      "#3b424d",
    "console":  "#0a0d11",

    # Hairlines / dividers
    "hl1":      "rgba(255,255,255,0.06)",
    "hl2":      "rgba(255,255,255,0.10)",
    "hl3":      "rgba(255,255,255,0.16)",

    # Text
    "t1":       "#e6e8eb",
    "t2":       "#b8bdc6",
    "t3":       "#8b919c",
    "t4":       "#5d626c",

    # Accent (cyan; can be re-tinted at runtime)
    "accent":       "#4dc3ff",
    "accent_rgb":   "77, 195, 255",
    "accent_soft":  "rgba(77,195,255,0.18)",
    "accent_glow":  "rgba(77,195,255,0.55)",

    # Semantic
    "ok":     "#5acf6c",  "ok_rgb":   "90, 207, 108",
    "warn":   "#f0b541",  "warn_rgb": "240, 181, 65",
    "err":    "#ef5b66",  "err_rgb":  "239, 91, 102",
    "info":   "#6aa1ff",  "info_rgb": "106, 161, 255",

    # Log line tints
    "log_time": "#6e7681",
    "log_info": "#88a2c4",
    "log_ok":   "#6ed27f",
    "log_warn": "#e7b85c",
    "log_err":  "#ef6f78",
    "log_dim":  "#5a6068",
    "log_pkt":  "#c08fff",
    "log_tg":   "#65b8e8",
}

# Accent tints (for runtime "accent" picker — same options as designer prototype).
ACCENTS: dict[str, dict[str, str]] = {
    "cyan":   {"c": "#4dc3ff", "rgb": "77, 195, 255",  "soft": "rgba(77,195,255,0.18)",  "glow": "rgba(77,195,255,0.55)"},
    "green":  {"c": "#5acf6c", "rgb": "90, 207, 108",  "soft": "rgba(90,207,108,0.18)",  "glow": "rgba(90,207,108,0.55)"},
    "amber":  {"c": "#e8a93b", "rgb": "232, 169, 59",  "soft": "rgba(232,169,59,0.18)",  "glow": "rgba(232,169,59,0.55)"},
    "violet": {"c": "#a988e5", "rgb": "169, 136, 229", "soft": "rgba(169,136,229,0.18)", "glow": "rgba(169,136,229,0.55)"},
    "red":    {"c": "#e85a5a", "rgb": "232, 90, 90",   "soft": "rgba(232,90,90,0.18)",   "glow": "rgba(232,90,90,0.55)"},
}


def set_accent(name: str) -> None:
    """Mutate PALETTE in place to switch accent. Re-call apply_theme afterwards."""
    a = ACCENTS.get(name) or ACCENTS["cyan"]
    PALETTE["accent"] = a["c"]
    PALETTE["accent_rgb"] = a["rgb"]
    PALETTE["accent_soft"] = a["soft"]
    PALETTE["accent_glow"] = a["glow"]


# ---------------------------------------------------------------------------
# QSS template
# ---------------------------------------------------------------------------
QSS_TEMPLATE = """
* {{
    outline: none;
}}

QMainWindow, QDialog, QWidget {{
    background: {bg1};
    color: {t1};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 12px;
}}

QToolTip {{
    background: {bg3};
    color: {t1};
    border: 1px solid {bg5};
    padding: 4px 6px;
}}

/* ── menu bar (top of main window) ─────────────────────────────────── */
QMenuBar {{
    background: {bg1};
    color: {t2};
    border-bottom: 1px solid rgba(255,255,255,0.06);
    padding: 0 4px;
    font-size: 12px;
}}
QMenuBar::item {{
    padding: 4px 9px;
    background: transparent;
    color: {t2};
}}
QMenuBar::item:selected, QMenuBar::item:pressed {{
    background: {bg4};
    color: {t1};
}}

QMenu {{
    background: #1f242b;
    color: {t1};
    border: 1px solid #0c0e11;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 22px 5px 24px;
    color: {t1};
    font-size: 12px;
}}
QMenu::item:selected {{
    background: {accent};
    color: #06121b;
}}
QMenu::separator {{
    height: 1px;
    background: rgba(255,255,255,0.10);
    margin: 4px 6px;
}}
QMenu::icon {{
    padding-left: 6px;
}}

/* ── statusbar at the bottom of main window ────────────────────────── */
QStatusBar {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #21262d, stop:1 #1a1e23);
    border-top: 1px solid #0e1115;
    color: {t3};
    font-family: "Consolas", "JetBrains Mono", monospace;
    font-size: 10.5px;
}}
QStatusBar::item {{ border: none; }}

/* ── group box (Qt-style frame with title) ─────────────────────────── */
QGroupBox {{
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 3px;
    margin-top: 14px;
    padding-top: 12px;
    background: rgba(255,255,255,0.005);
    font-size: 11px;
    color: {t3};
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    margin-left: 10px;
    background: {bg2};
}}

/* ── Buttons ───────────────────────────────────────────────────────── */
QPushButton {{
    height: 26px;
    padding: 0 10px;
    color: {t1};
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {bg3}, stop:1 #252a31);
    border: 1px solid #14171c;
    border-radius: 3px;
    font-size: 12px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {bg4}, stop:1 #2c333d);
    border-color: #1a1e23;
}}
QPushButton:pressed {{
    background: {bg3};
}}
QPushButton:disabled {{
    color: {t4};
    background: {bg2};
    border-color: rgba(255,255,255,0.06);
}}
QPushButton[role="primary"] {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {accent}, stop:1 #2a8fbf);
    color: #06121b;
    border: 1px solid #1a3a52;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {accent}, stop:1 #3aa1d1);
}}
QPushButton[role="danger"] {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {err}, stop:1 #c43b48);
    color: #ffffff;
    border: 1px solid #6f1e26;
    font-weight: 600;
}}
QPushButton[role="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {t2};
}}
QPushButton[role="ghost"]:hover {{
    background: {bg3};
    color: {t1};
}}

/* ── Inputs ────────────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: #161a1f;
    border: 1px solid #0a0c0f;
    border-radius: 3px;
    padding: 4px 8px;
    color: {t1};
    selection-background-color: {accent_soft};
    selection-color: {t1};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {accent};
}}
QLineEdit:disabled {{
    color: {t4};
    background: {bg2};
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 14px;
    background: {bg3};
    border: none;
}}

QComboBox {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1f242b, stop:1 #181c22);
    border: 1px solid #0a0c0f;
    border-radius: 3px;
    padding: 4px 22px 4px 8px;
    color: {t1};
    min-height: 18px;
    font-family: "Consolas", monospace;
    font-size: 11.5px;
}}
QComboBox:hover {{
    border-color: #1a1e23;
}}
QComboBox:focus, QComboBox:on {{
    border-color: {accent};
}}
QComboBox::drop-down {{
    width: 22px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 4px solid {t3};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: #1f242b;
    border: 1px solid #0c0e11;
    color: {t1};
    selection-background-color: {accent};
    selection-color: #06121b;
    padding: 4px 0;
    outline: none;
}}

/* ── checkbox / radio ──────────────────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {t1};
    spacing: 6px;
    font-size: 11.5px;
}}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    background: #161a1f;
    border: 1px solid #2a3038;
    border-radius: 2px;
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: none;
}}
QRadioButton::indicator {{
    width: 13px; height: 13px;
    border: 1px solid #2a3038;
    border-radius: 7px;
    background: #161a1f;
}}
QRadioButton::indicator:checked {{
    border-color: {accent};
    background: qradialgradient(cx:0.5,cy:0.5,radius:0.5,
                                stop:0 {accent}, stop:0.55 {accent}, stop:0.6 transparent);
}}

/* ── tabs ──────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid rgba(255,255,255,0.10);
    background: {bg1};
    top: -1px;
}}
QTabBar {{
    background: {bg2};
    border-bottom: 1px solid rgba(255,255,255,0.10);
}}
QTabBar::tab {{
    padding: 7px 14px;
    color: {t3};
    background: transparent;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    font-size: 11.5px;
}}
QTabBar::tab:hover {{
    color: {t1};
    background: rgba(255,255,255,0.02);
}}
QTabBar::tab:selected {{
    color: {t1};
    background: {bg1};
    border-color: rgba(255,255,255,0.10);
    border-top: 2px solid {accent};
}}

/* ── splitter ──────────────────────────────────────────────────────── */
QSplitter::handle:horizontal {{
    background: {bg2};
    width: 4px;
}}
QSplitter::handle:horizontal:hover {{
    background: {accent_soft};
}}

/* ── scrollbars ────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #2a3038;
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {bg5};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: #2a3038;
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── tables (Users / Slots) ────────────────────────────────────────── */
QTableWidget, QTableView {{
    background: #161a1f;
    alternate-background-color: rgba(255,255,255,0.012);
    gridline-color: rgba(255,255,255,0.06);
    color: {t1};
    selection-background-color: {accent_soft};
    selection-color: {t1};
    border: 1px solid #0e1115;
    font-size: 11.5px;
}}
QHeaderView::section {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #2a3038, stop:1 #21262d);
    color: {t2};
    border: none;
    border-right: 1px solid rgba(255,255,255,0.06);
    border-bottom: 1px solid #0e1115;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
}}
QTableView::item {{
    padding: 0 6px;
}}
QTableView::item:hover {{
    background: rgba(77,195,255,0.06);
}}

/* ── list widget (used for sidebar + lists) ────────────────────────── */
QListWidget {{
    background: {bg2};
    border: none;
    color: {t2};
    padding: 4px;
    outline: none;
    font-size: 11.5px;
}}
QListWidget::item {{
    padding: 6px 10px;
    border-radius: 3px;
    margin: 1px 0;
}}
QListWidget::item:hover {{
    background: rgba(255,255,255,0.03);
    color: {t1};
}}
QListWidget::item:selected {{
    background: {accent_soft};
    color: {t1};
    border-left: 2px solid {accent};
}}

/* ── progress bar ──────────────────────────────────────────────────── */
QProgressBar {{
    height: 6px;
    background: #0d1115;
    border: 1px solid #050608;
    border-radius: 3px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {accent}, stop:1 #88d8ff);
    border-radius: 2px;
}}

/* ── tool bar ──────────────────────────────────────────────────────── */
QToolBar {{
    background: {bg2};
    border: none;
    border-bottom: 1px solid #14181d;
    padding: 4px 6px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: rgba(255,255,255,0.10);
    width: 1px;
    margin: 4px 4px;
}}
QToolButton {{
    background: transparent;
    color: {t2};
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 11.5px;
}}
QToolButton:hover {{
    background: {bg4};
    color: {t1};
    border-color: rgba(255,255,255,0.06);
}}
QToolButton:pressed {{
    background: {bg5};
}}
QToolButton:checked {{
    background: {accent_soft};
    color: {accent};
}}
"""


def _resolve(template: str) -> str:
    return template.format(**PALETTE)


def apply_theme(app: QApplication) -> None:
    """Install the QSS + a matching dark QPalette on the application."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,         QColor(PALETTE["bg1"]))
    pal.setColor(QPalette.ColorRole.WindowText,     QColor(PALETTE["t1"]))
    pal.setColor(QPalette.ColorRole.Base,           QColor(PALETTE["bg2"]))
    pal.setColor(QPalette.ColorRole.AlternateBase,  QColor(PALETTE["bg3"]))
    pal.setColor(QPalette.ColorRole.Text,           QColor(PALETTE["t1"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(PALETTE["t3"]))
    pal.setColor(QPalette.ColorRole.Button,         QColor(PALETTE["bg3"]))
    pal.setColor(QPalette.ColorRole.ButtonText,     QColor(PALETTE["t1"]))
    pal.setColor(QPalette.ColorRole.Highlight,      QColor(PALETTE["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#06121b"))
    pal.setColor(QPalette.ColorRole.ToolTipBase,    QColor(PALETTE["bg3"]))
    pal.setColor(QPalette.ColorRole.ToolTipText,    QColor(PALETTE["t1"]))
    app.setPalette(pal)
    app.setStyleSheet(_resolve(QSS_TEMPLATE))


def palette_qss() -> str:
    """Return the resolved QSS string (for ad-hoc widget application)."""
    return _resolve(QSS_TEMPLATE)
