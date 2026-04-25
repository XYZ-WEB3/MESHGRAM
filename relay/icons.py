"""
SVG icons ported from out_dis/app/icons.jsx.

Each icon is a 24x24 viewBox snippet. `make_icon(name, color="...")` returns
a `QIcon` painted at the requested colour at high DPI.
"""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# All paths use stroke="currentColor"; we substitute on render.
_ICON_BODIES: dict[str, str] = {
    # --- base ui ---
    "play":     '<polygon points="6 4 20 12 6 20 6 4" fill="currentColor" stroke="none"/>',
    "stop":     '<rect x="5" y="5" width="14" height="14" rx="1" fill="currentColor" stroke="none"/>',
    "pause":    '<rect x="6" y="5" width="4" height="14" fill="currentColor" stroke="none"/>'
                '<rect x="14" y="5" width="4" height="14" fill="currentColor" stroke="none"/>',
    "refresh":  '<path d="M3 12a9 9 0 0115.5-6.3M21 4v5h-5"/>'
                '<path d="M21 12a9 9 0 01-15.5 6.3M3 20v-5h5"/>',
    "settings": '<circle cx="12" cy="12" r="2.5"/>'
                '<path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06'
                'a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09'
                'A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83'
                'l.06-.06A1.65 1.65 0 004.6 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09'
                'A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83'
                'l.06.06a1.65 1.65 0 001.82.33H9A1.65 1.65 0 0010 3.09V3a2 2 0 014 0v.09'
                'a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83'
                'l-.06.06A1.65 1.65 0 0019.4 9c.05.49.36.91.81 1.13.45.21.96.21 1.41 0H21'
                'a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>',
    "search":   '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "close":    '<path d="M18 6L6 18M6 6l12 12"/>',
    "minimize": '<path d="M5 19h14"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="0.5"/>',
    "chevDown": '<polyline points="6 9 12 15 18 9" fill="none"/>',
    "chevRight":'<polyline points="9 6 15 12 9 18" fill="none"/>',
    "chevLeft": '<polyline points="15 6 9 12 15 18" fill="none"/>',
    "plus":     '<path d="M12 5v14M5 12h14"/>',
    "minus":    '<path d="M5 12h14"/>',
    "trash":    '<path d="M3 6h18"/>'
                '<path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>'
                '<path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>',
    "edit":     '<path d="M12 20h9"/>'
                '<path d="M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4 12.5-12.5z"/>',
    "copy":     '<rect x="9" y="9" width="13" height="13" rx="2"/>'
                '<path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>',
    "download": '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>'
                '<polyline points="7 10 12 15 17 10"/><path d="M12 15V3"/>',
    "upload":   '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>'
                '<polyline points="17 8 12 3 7 8"/><path d="M12 3v12"/>',
    # --- domain ---
    "usb":      '<path d="M12 2v15"/><circle cx="12" cy="20" r="2"/>'
                '<path d="M7 12l5-5 5 5"/>'
                '<path d="M7 12v3a2 2 0 002 2h6a2 2 0 002-2v-3"/>',
    "radio":    '<circle cx="12" cy="12" r="2"/>'
                '<path d="M16.24 7.76a6 6 0 010 8.49"/>'
                '<path d="M7.76 16.24a6 6 0 010-8.49"/>'
                '<path d="M19.07 4.93a10 10 0 010 14.14"/>'
                '<path d="M4.93 19.07a10 10 0 010-14.14"/>',
    "bot":      '<rect x="3" y="8" width="18" height="12" rx="2"/>'
                '<circle cx="8" cy="14" r="1.2" fill="currentColor"/>'
                '<circle cx="16" cy="14" r="1.2" fill="currentColor"/>'
                '<path d="M12 4v4"/><circle cx="12" cy="3" r="1" fill="currentColor"/>'
                '<path d="M8 20v2M16 20v2"/>',
    "user":     '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>',
    "users":    '<circle cx="9" cy="8" r="3.5"/><path d="M2 21a7 7 0 0114 0"/>'
                '<path d="M16 4.5a3.5 3.5 0 010 7"/><path d="M22 21a7 7 0 00-6-6.93"/>',
    "shield":   '<path d="M12 2l8 3v6c0 5-3.5 9.5-8 11-4.5-1.5-8-6-8-11V5l8-3z"/>',
    "shieldCheck": '<path d="M12 2l8 3v6c0 5-3.5 9.5-8 11-4.5-1.5-8-6-8-11V5l8-3z"/>'
                   '<polyline points="9 12 11 14 15 10"/>',
    "star":     '<polygon points="12 2 15 9 22 10 17 15 18 22 12 19 6 22 7 15 2 10 9 9 12 2"/>',
    "ban":      '<circle cx="12" cy="12" r="10"/><line x1="5" y1="5" x2="19" y2="19"/>',
    "pin":      '<path d="M12 13v8"/><path d="M5 7l5 5 4-4-5-5"/>'
                '<path d="M9 12l-5 5"/><path d="M14 8l5-5"/>',
    "gps":      '<circle cx="12" cy="12" r="3"/>'
                '<path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    "alert":    '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>'
                '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "link":     '<path d="M10 14a5 5 0 007.07 0l3-3a5 5 0 00-7.07-7.07l-1 1"/>'
                '<path d="M14 10a5 5 0 00-7.07 0l-3 3a5 5 0 007.07 7.07l1-1"/>',
    "list":     '<line x1="8" y1="6" x2="21" y2="6"/>'
                '<line x1="8" y1="12" x2="21" y2="12"/>'
                '<line x1="8" y1="18" x2="21" y2="18"/>'
                '<circle cx="4" cy="6" r="0.5" fill="currentColor"/>'
                '<circle cx="4" cy="12" r="0.5" fill="currentColor"/>'
                '<circle cx="4" cy="18" r="0.5" fill="currentColor"/>',
    "inbox":    '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
                '<path d="M5.45 5.11L2 12v6a2 2 0 002 2h16a2 2 0 002-2v-6l-3.45-6.89A2 2 0 0016.76 4H7.24a2 2 0 00-1.79 1.11z"/>',
    "cat":      '<rect x="3" y="4" width="18" height="4" rx="1"/>'
                '<rect x="3" y="10" width="18" height="4" rx="1"/>'
                '<rect x="3" y="16" width="18" height="4" rx="1"/>',
    "filter":   '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "clock":    '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "send":     '<path d="M22 2L11 13"/>'
                '<path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
    "sliders":  '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/>'
                '<line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/>'
                '<line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/>'
                '<line x1="1" y1="14" x2="7" y2="14"/>'
                '<line x1="9" y1="8" x2="15" y2="8"/>'
                '<line x1="17" y1="16" x2="23" y2="16"/>',
    "info":     '<circle cx="12" cy="12" r="10"/>'
                '<line x1="12" y1="16" x2="12" y2="12"/>'
                '<line x1="12" y1="8" x2="12.01" y2="8"/>',
    "check":    '<polyline points="20 6 9 17 4 12"/>',
    "wand":     '<path d="M15 4l5 5"/><path d="M3 21l9-9"/>'
                '<path d="M14 5l5 5"/><path d="M19 14l2 2-3 3-2-2"/>'
                '<path d="M5 8l2-2"/>',
    "eye":      '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
                '<circle cx="12" cy="12" r="3"/>',
    "eyeOff":   '<path d="M17.94 17.94A10.94 10.94 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>'
                '<path d="M9.9 4.24A10.94 10.94 0 0112 4c7 0 11 8 11 8a18.51 18.51 0 01-2.16 3.19"/>'
                '<path d="M14.12 14.12a3 3 0 11-4.24-4.24"/>'
                '<line x1="1" y1="1" x2="23" y2="23"/>',
    "bell":     '<path d="M18 8a6 6 0 00-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>'
                '<path d="M13.73 21a2 2 0 01-3.46 0"/>',
    "power":    '<path d="M18.36 6.64a9 9 0 11-12.73 0"/>'
                '<line x1="12" y1="2" x2="12" y2="12"/>',
    "pkg":      '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>'
                '<polyline points="3.27 6.96 12 12.01 20.73 6.96"/>'
                '<line x1="12" y1="22.08" x2="12" y2="12"/>',
    "python":   '<path d="M12 4c-3 0-3 1-3 2v2h6V7H10"/>'
                '<path d="M12 20c3 0 3-1 3-2v-2H9v1h5"/>'
                '<rect x="6" y="8" width="12" height="8" rx="2"/>',
}


def _svg(body: str, color: str, fill_default: str = "none") -> str:
    """Return a full SVG document with the given stroke colour."""
    coloured = body.replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="{fill_default}" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round">{coloured}</svg>'
    )


def make_icon(name: str, color: str = "#b8bdc6", size: int = 16) -> QIcon:
    """Render an SVG icon to a high-DPI QIcon."""
    body = _ICON_BODIES.get(name)
    if body is None:
        return QIcon()
    svg = _svg(body, color).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg))
    pix = QPixmap(QSize(size * 2, size * 2))  # 2× for HiDPI
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    pix.setDevicePixelRatio(2.0)
    icon = QIcon()
    icon.addPixmap(pix)
    return icon


def icon_names() -> list[str]:
    return sorted(_ICON_BODIES.keys())
