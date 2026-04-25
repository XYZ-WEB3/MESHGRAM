"""
Custom widgets — port of designer's reusable components.

GlowDot, StatusCell, NodePanel, ToolBtn, LogConsole.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import (
    QByteArray,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    QTimer,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from theme import PALETTE
from icons import make_icon
import devices as _devices


def render_svg_to_pixmap(svg_path, size, dpr: float = 2.0) -> QPixmap:
    """Render an SVG file to a HiDPI QPixmap, preserving aspect ratio
    (centered, with transparent margins). Used by the device preview in
    NodePanel and SettingsDialog."""
    data = svg_path.read_bytes()
    renderer = QSvgRenderer(QByteArray(data))
    w_px = int(size.width() * dpr)
    h_px = int(size.height() * dpr)
    pix = QPixmap(w_px, h_px)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    sz = renderer.defaultSize()
    if sz.width() > 0 and sz.height() > 0 and w_px > 0 and h_px > 0:
        src_aspect = sz.width() / sz.height()
        tgt_aspect = w_px / h_px
        if src_aspect > tgt_aspect:
            tw = w_px
            th = int(w_px / src_aspect)
        else:
            th = h_px
            tw = int(h_px * src_aspect)
        x = (w_px - tw) // 2
        y = (h_px - th) // 2
        renderer.render(painter, QRectF(x, y, tw, th))
    else:
        renderer.render(painter)
    painter.end()
    pix.setDevicePixelRatio(dpr)
    return pix

_TONE_COLORS = {
    "ok":   PALETTE["ok"],
    "warn": PALETTE["warn"],
    "err":  PALETTE["err"],
    "info": PALETTE["info"],
    "off":  "#444a55",
}


# ---------------------------------------------------------------------------
# GlowDot — pulsing status indicator
# ---------------------------------------------------------------------------
class GlowDot(QWidget):
    """Small (7px) coloured circle. Optional pulse animation when `live=True`."""

    def __init__(self, tone: str = "off", live: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tone = tone
        self._live = live
        self._pulse = 0.0
        self.setFixedSize(14, 14)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(1600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        if live:
            self._anim.start()

    def setTone(self, tone: str) -> None:
        if tone != self._tone:
            self._tone = tone
            self.update()

    def setLive(self, live: bool) -> None:
        if live == self._live:
            return
        self._live = live
        if live:
            self._anim.start()
        else:
            self._anim.stop()
            self._pulse = 0.0
        self.update()

    def get_pulse(self) -> float:
        return self._pulse

    def set_pulse(self, v: float) -> None:
        self._pulse = v
        self.update()

    pulse = pyqtProperty(float, fget=get_pulse, fset=set_pulse)

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(_TONE_COLORS.get(self._tone, "#444a55"))
        cx, cy = self.width() / 2, self.height() / 2
        # Solid dot
        r = 3.5
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        if self._tone != "off":
            # Static glow halo
            halo = QColor(col)
            halo.setAlphaF(0.35)
            p.setBrush(halo)
            r2 = 5
            p.drawEllipse(QRectF(cx - r2, cy - r2, 2 * r2, 2 * r2))
        if self._live and self._tone != "off":
            # Pulse ring — expanding + fading
            pr = 4 + self._pulse * 4
            alpha = max(0.0, 1.0 - self._pulse)
            ring = QColor(col)
            ring.setAlphaF(alpha * 0.7)
            pen = QPen(ring, 1.2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, 2 * pr, 2 * pr))
        p.end()


# ---------------------------------------------------------------------------
# StatusCell — pill in status bar / status row
# ---------------------------------------------------------------------------
class StatusCell(QFrame):
    """A status-bar cell with an optional GlowDot, label and tone-driven color."""

    clicked = pyqtSignal()

    def __init__(self, label: str = "", tone: str = "off", live: bool = False,
                 with_dot: bool = True, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tone = tone
        self.setObjectName("StatusCell")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(
            "#StatusCell { background: transparent; padding: 0 10px; "
            "border-right: 1px solid rgba(255,255,255,0.06); }"
            "#StatusCell:hover { background: rgba(255,255,255,0.03); }"
        )

        h = QHBoxLayout(self)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(6)
        self._dot = GlowDot(tone, live=live)
        if not with_dot:
            self._dot.hide()
        h.addWidget(self._dot)
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            f"QLabel {{ color: {PALETTE['t3']}; "
            f"font-family: 'Consolas', monospace; font-size: 10.5px; }}"
        )
        h.addWidget(self._lbl)
        self.setFixedHeight(22)

    def setLabel(self, text: str) -> None:
        self._lbl.setText(text)

    def setTone(self, tone: str, live: Optional[bool] = None) -> None:
        self._tone = tone
        self._dot.setTone(tone)
        if live is not None:
            self._dot.setLive(live)

    def setLive(self, live: bool) -> None:
        self._dot.setLive(live)

    def mouseReleaseEvent(self, ev) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


# ---------------------------------------------------------------------------
# ToolBtn — toolbar push-button with icon + optional label + role
# ---------------------------------------------------------------------------
class ToolBtn(QPushButton):
    """A QPushButton that auto-loads an icon by name and supports roles
    ('primary', 'danger', 'ghost') matching the theme."""

    def __init__(self, icon_name: str = "", label: str = "", role: str = "",
                 size: int = 14, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._role = role
        if role:
            self.setProperty("role", role)
        if icon_name:
            self.setIcon(make_icon(icon_name, color=self._icon_color(), size=size))
            self.setIconSize(QSize(size, size))
        if label:
            self.setText("  " + label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _icon_color(self) -> str:
        if self._role == "primary":
            return "#06121b"
        if self._role == "danger":
            return "#ffffff"
        return PALETTE["t2"]


# ---------------------------------------------------------------------------
# NodePanel — "home node" card on the right side of the main window
# ---------------------------------------------------------------------------
class NodePanel(QFrame):
    """Right-side card showing the home node: device SVG + ID + KPI grid."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("NodePanel")
        self.setStyleSheet(
            "#NodePanel { "
            f"background: rgba(77,195,255,0.06); "
            f"border: 1px solid {PALETTE['hl2']}; "
            "border-radius: 4px; }"
        )
        self._current_model: Optional[str] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        # Device picture (SVG of the selected model, large, full-width)
        self._pic = QLabel()
        self._pic.setFixedHeight(170)
        self._pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pic.setStyleSheet(
            "QLabel { background: #0d1115; border: 1px solid rgba(255,255,255,0.06); "
            "border-radius: 4px; color: %s; font-size: 11px; }" % PALETTE['t3']
        )
        v.addWidget(self._pic)

        # Title row: model label + status dot
        head = QHBoxLayout()
        head.setSpacing(9)
        self._title = QLabel("home node")
        self._title.setStyleSheet(
            f"color: {PALETTE['t1']}; font-weight: 600; font-size: 12px;"
        )
        head.addWidget(self._title, 1)
        self._dot = GlowDot("off")
        head.addWidget(self._dot)
        v.addLayout(head)

        self._sub = QLabel("—")
        self._sub.setStyleSheet(
            f"color: {PALETTE['t3']}; font-family: 'Consolas', monospace; font-size: 10px;"
        )
        v.addWidget(self._sub)

        # KPI cells
        self._stats: dict[str, QLabel] = {}
        grid = QHBoxLayout()
        grid.setSpacing(4)
        for key, cap_text in [("port", "ПОРТ"), ("slots", "СЛОТЫ"),
                              ("wl", "WL"), ("uptime", "АПТАЙМ")]:
            cell = QFrame()
            cell.setStyleSheet(
                "QFrame { background: #161a1f; "
                f"border: 1px solid {PALETTE['hl1']}; border-radius: 3px; }}"
            )
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(7, 5, 7, 5)
            cl.setSpacing(0)
            cap = QLabel(cap_text)
            cap.setStyleSheet(
                f"color: {PALETTE['t3']}; font-size: 9px; letter-spacing: 1px;"
            )
            val = QLabel("—")
            val.setStyleSheet(
                f"color: {PALETTE['t1']}; font-size: 11px; font-family: 'Consolas', monospace;"
            )
            cl.addWidget(cap)
            cl.addWidget(val)
            self._stats[key] = val
            grid.addWidget(cell, 1)
        v.addLayout(grid)

        # Initial empty pic
        self._render_pic("generic")

    def _render_pic(self, model_id: str) -> None:
        if model_id == self._current_model and self._pic.pixmap() is not None and not self._pic.pixmap().isNull():
            return
        self._current_model = model_id
        svg_path = _devices.get_svg_path(model_id)
        if svg_path is None:
            self._pic.setPixmap(QPixmap())
            self._pic.setText("выбери модель устройства\nв Настройках → Устройство")
            return
        try:
            self._pic.setPixmap(render_svg_to_pixmap(svg_path, self._pic.size()))
            self._pic.setText("")
        except Exception:
            self._pic.setText("(не удалось загрузить картинку)")

    def update_state(self, *, com_port: str = "—", node_id: str = "—",
                     model_id: str = "generic",
                     slots: int = 0, wl: bool = False,
                     running: bool = False, uptime: str = "—") -> None:
        self._title.setText(_devices.get_label(model_id))
        self._sub.setText(f"{node_id} · {com_port}")
        self._stats["port"].setText(com_port)
        self._stats["slots"].setText(str(slots))
        self._stats["wl"].setText("ВКЛ" if wl else "выкл")
        self._stats["uptime"].setText(uptime if running else "—")
        self._dot.setTone("ok" if running else "off")
        self._dot.setLive(running)
        self._render_pic(model_id)


# ---------------------------------------------------------------------------
# LogConsole — colored log view
# ---------------------------------------------------------------------------
_LOG_TAG_RE = re.compile(r"\[(?P<tag>[a-z]+)\]", re.IGNORECASE)
_LOG_TIME_RE = re.compile(r"^(?P<ts>\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)")
_LOG_LEVEL_KEYWORDS = {
    "ERROR":   "err",
    "ERR":     "err",
    "CRITICAL":"err",
    "TRACEBACK": "err",
    "WARN":    "warn",
    "WARNING": "warn",
    "INFO":    "info",
    "DEBUG":   "dim",
}
_TAG_TINTS = {
    "info":    PALETTE["log_info"],
    "ok":      PALETTE["log_ok"],
    "warn":    PALETTE["log_warn"],
    "err":     PALETTE["log_err"],
    "dim":     PALETTE["log_dim"],
    "pkt":     PALETTE["log_pkt"],
    "mesh":    PALETTE["log_pkt"],
    "tg":      PALETTE["log_tg"],
    "telegram":PALETTE["log_tg"],
    "settings":PALETTE["log_info"],
    "db":      PALETTE["log_dim"],
    "slots":   PALETTE["accent"],
    "relay":   PALETTE["log_ok"],
    "wl":      PALETTE["log_warn"],
    "gps":     PALETTE["log_pkt"],
}


class LogConsole(QTextEdit):
    """Read-only text edit with per-line tag colouring + grid background."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet(
            f"QTextEdit {{ background: {PALETTE['console']}; color: #c8cdd4; "
            "border: 1px solid #050608; border-radius: 3px; "
            "padding: 8px 12px; }}"
        )
        self.document().setMaximumBlockCount(2000)  # cap memory

    def append_raw(self, text: str) -> None:
        """Append a chunk of stdout/stderr (may contain newlines).
        Each line is parsed for [tag] / level keywords and tinted accordingly.
        """
        if not text:
            return
        for line in text.splitlines():
            self._append_line(line)

    def _append_line(self, line: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        if not line.strip():
            cursor.insertText("\n")
            return

        # Tone heuristic: explicit level keyword wins, then [tag], then info default.
        tone_color = PALETTE["log_info"]
        upper = line.upper()
        for kw, t in _LOG_LEVEL_KEYWORDS.items():
            if kw in upper:
                tone_color = _TAG_TINTS.get(t, tone_color)
                break
        m_tag = _LOG_TAG_RE.search(line)
        if m_tag:
            tag = m_tag.group("tag").lower()
            tone_color = _TAG_TINTS.get(tag, tone_color)

        ts_fmt = QTextCharFormat()
        ts_fmt.setForeground(QColor(PALETTE["log_time"]))
        body_fmt = QTextCharFormat()
        body_fmt.setForeground(QColor(tone_color if line.strip() else "#c8cdd4"))

        # Prepend timestamp if line doesn't already start with one.
        m_ts = _LOG_TIME_RE.match(line)
        if not m_ts:
            ts = datetime.now().strftime("%H:%M:%S")
            cursor.setCharFormat(ts_fmt)
            cursor.insertText(f"{ts}  ")
            cursor.setCharFormat(body_fmt)
            cursor.insertText(line + "\n")
            return

        cursor.setCharFormat(ts_fmt)
        cursor.insertText(m_ts.group("ts"))
        cursor.setCharFormat(body_fmt)
        cursor.insertText(line[m_ts.end():] + "\n")
        # Auto-scroll
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear_log(self) -> None:
        self.clear()


# ---------------------------------------------------------------------------
# ToolSep — vertical divider for tool bar
# ---------------------------------------------------------------------------
class ToolSep(QFrame):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.VLine)
        self.setFixedWidth(1)
        self.setStyleSheet(
            f"QFrame {{ background: {PALETTE['hl2']}; border: none; "
            "margin: 4px 6px; }}"
        )


# ---------------------------------------------------------------------------
# Badge — small inline pill (used in tables / details panes)
# ---------------------------------------------------------------------------
class Badge(QLabel):
    TONES = {
        "wl":   ("ok",   "WL"),
        "fav":  ("warn", "FAV"),
        "ban":  ("err",  "BAN"),
        "cat":  ("info", ""),
        "muted":("dim",  ""),
    }

    def __init__(self, kind: str, text: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        tone, default = self.TONES.get(kind, ("info", ""))
        if tone == "dim":
            color = PALETTE["t3"]
            border = PALETTE["hl2"]
            bg = PALETTE["bg3"]
        else:
            color_key = {
                "ok": "ok_rgb", "warn": "warn_rgb", "err": "err_rgb", "info": "info_rgb"
            }[tone]
            base = PALETTE[tone]
            rgb = PALETTE[color_key]
            color = base
            border = f"rgba({rgb}, 0.30)"
            bg = f"rgba({rgb}, 0.14)"
        self.setText((text or default).upper())
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: {bg}; "
            f"border: 1px solid {border}; "
            "padding: 1px 6px; border-radius: 2px; "
            "font-family: 'Consolas', monospace; font-size: 10px; "
            "font-weight: 600; letter-spacing: 1px; }}"
        )
