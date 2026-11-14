"""Visual design system, Dark/Light QSS themes, and crisp programmatic SVG icons."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from link_downloader.core.enums import ThemeMode

_ICON_PATHS: dict[str, str] = {
    "download": (
        '<path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" fill="none"/>'
    ),
    "queue": (
        '<path d="M4 7h16M4 12h12M4 17h8" stroke="{c}" stroke-width="2.1" stroke-linecap="round"/>'
        '<circle cx="18" cy="17" r="3" stroke="{c}" stroke-width="2.1" fill="none"/>'
    ),
    "history": (
        '<path d="M3 12a9 9 0 1 0 3-6.7L3 8" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        '<path d="M3 3v5h5M12 7v5l3 2" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3" stroke="{c}" stroke-width="2.1" fill="none"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06'
        'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09'
        'a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06'
        'a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09'
        'a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06'
        'a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09'
        'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06'
        'a1.65 1.65 0 0 0-.33 1.82V9c.26.6.85 1 1.51 1H21a2 2 0 1 1 0 4h-.09'
        'a1.65 1.65 0 0 0-1.51 1z" stroke="{c}" stroke-width="1.8" fill="none"/>'
    ),
    "paste": (
        '<rect x="8" y="3" width="8" height="4" rx="1" stroke="{c}" stroke-width="2" fill="none"/>'
        '<path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" '
        'stroke="{c}" stroke-width="2" stroke-linecap="round" fill="none"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="7" stroke="{c}" stroke-width="2.1" fill="none"/>'
        '<path d="m20 20-3.8-3.8" stroke="{c}" stroke-width="2.1" stroke-linecap="round"/>'
    ),
    "clear": (
        '<path d="M18 6 6 18M6 6l12 12" stroke="{c}" stroke-width="2.1" stroke-linecap="round"/>'
    ),
    "folder": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" '
        'stroke="{c}" stroke-width="2" stroke-linejoin="round" fill="none"/>'
    ),
    "file": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" '
        'stroke="{c}" stroke-width="2" stroke-linejoin="round" fill="none"/>'
        '<path d="M14 3v5h5" stroke="{c}" stroke-width="2" stroke-linejoin="round" fill="none"/>'
    ),
    "link": (
        '<path d="M10 13a5 5 0 0 0 7.54.54l2.12-2.12a5 5 0 0 0-7.07-7.07L11.4 5.5" '
        'stroke="{c}" stroke-width="2.1" stroke-linecap="round" fill="none"/>'
        '<path d="M14 11a5 5 0 0 0-7.54-.54L4.34 12.58a5 5 0 0 0 7.07 7.07l1.19-1.15" '
        'stroke="{c}" stroke-width="2.1" stroke-linecap="round" fill="none"/>'
    ),
    "pause": (
        '<rect x="6" y="5" width="4" height="14" rx="1" fill="{c}"/>'
        '<rect x="14" y="5" width="4" height="14" rx="1" fill="{c}"/>'
    ),
    "play": '<path d="M7 5l12 7-12 7V5z" fill="{c}"/>',
    "retry": (
        '<path d="M21 12a9 9 0 1 1-2.64-6.36" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" fill="none"/>'
        '<path d="M21 3v6h-6" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    ),
    "warning": (
        '<path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.4 0z" '
        'stroke="{c}" stroke-width="2" stroke-linejoin="round" fill="none"/>'
        '<path d="M12 9v4M12 17h.01" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>'
    ),
    "check": (
        '<path d="m20 6-11 11-5-5" stroke="{c}" stroke-width="2.3" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    ),
    "trash": (
        '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" '
        'stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    ),
}


def make_icon(name: str, color: str = "#cbd5e1", size: int = 20) -> QIcon:
    """Render a crisp HiDPI QIcon from an inline SVG icon definition."""
    body = _ICON_PATHS.get(name, _ICON_PATHS["link"]).format(c=color)
    svg_str = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return QIcon(pixmap)


def get_theme_palette(mode: ThemeMode | str) -> dict[str, str]:
    """Return color tokens for Dark or Light mode."""
    is_light = str(mode).lower() == ThemeMode.LIGHT.value
    if is_light:
        return {
            "bg": "#f4f6fb",
            "sidebar": "#ffffff",
            "card": "#ffffff",
            "input": "#f8fafc",
            "border": "#e2e8f0",
            "border_hover": "#cbd5e1",
            "text": "#0f172a",
            "text_secondary": "#475569",
            "text_muted": "#64748b",
            "accent": "#4f46e5",
            "accent_hover": "#4338ca",
            "accent_soft": "rgba(79, 70, 229, 0.12)",
            "accent_text": "#4338ca",
            "success": "#059669",
            "success_bg": "rgba(16, 185, 129, 0.12)",
            "warning": "#d97706",
            "warning_bg": "rgba(245, 158, 11, 0.14)",
            "danger": "#dc2626",
            "danger_bg": "rgba(239, 68, 68, 0.12)",
            "scroll_track": "#f1f5f9",
            "scroll_thumb": "#cbd5e1",
            "icon": "#475569",
        }
    return {
        "bg": "#0d0f14",
        "sidebar": "#131620",
        "card": "#181c28",
        "input": "#1f2435",
        "border": "#2a3047",
        "border_hover": "#3d4666",
        "text": "#f1f5f9",
        "text_secondary": "#94a3b8",
        "text_muted": "#64748b",
        "accent": "#6366f1",
        "accent_hover": "#4f46e5",
        "accent_soft": "rgba(99, 102, 241, 0.18)",
        "accent_text": "#a5b4fc",
        "success": "#34d399",
        "success_bg": "rgba(16, 185, 129, 0.16)",
        "warning": "#fbbf24",
        "warning_bg": "rgba(245, 158, 11, 0.16)",
        "danger": "#f87171",
        "danger_bg": "rgba(239, 68, 68, 0.16)",
        "scroll_track": "#131620",
        "scroll_thumb": "#333a54",
        "icon": "#cbd5e1",
    }


def build_stylesheet(mode: ThemeMode | str) -> str:
    """Generate the complete Qt Style Sheet (QSS) for Dark or Light mode."""
    p = get_theme_palette(mode)
    return f"""
    QMainWindow, QDialog {{
        background-color: {p['bg']};
        color: {p['text']};
    }}
    QWidget {{
        color: {p['text']};
        font-family: "Inter", "Segoe UI", "Noto Sans", system-ui, sans-serif;
        font-size: 13px;
    }}
    QWidget#Sidebar {{
        background-color: {p['sidebar']};
        border-right: 1px solid {p['border']};
    }}
    QFrame#Card, QGroupBox#Card {{
        background-color: {p['card']};
        border: 1px solid {p['border']};
        border-radius: 14px;
    }}
    QFrame#BannerWarning {{
        background-color: {p['warning_bg']};
        border: 1px solid {p['warning']};
        border-radius: 12px;
    }}
    QFrame#SubCard {{
        background-color: {p['input']};
        border: 1px solid {p['border']};
        border-radius: 10px;
    }}
    QLabel#PageTitle {{
        font-size: 20px;
        font-weight: 700;
        color: {p['text']};
    }}
    QLabel#SectionTitle {{
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.8px;
        color: {p['text_muted']};
    }}
    QLabel#MutedLabel {{
        color: {p['text_secondary']};
        font-size: 12px;
    }}
    QLabel#ErrorLabel {{
        color: {p['danger']};
        font-size: 12px;
        font-weight: 500;
    }}
    QLabel#SuccessLabel {{
        color: {p['success']};
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#NavButton {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 10px 14px;
        text-align: left;
        font-weight: 500;
        color: {p['text_secondary']};
    }}
    QPushButton#NavButton:hover {{
        background-color: {p['accent_soft']};
        color: {p['text']};
    }}
    QPushButton#NavButton:checked {{
        background-color: {p['accent_soft']};
        border: 1px solid {p['accent']};
        color: {p['accent_text']};
        font-weight: 600;
    }}
    QPushButton#PrimaryButton {{
        background-color: {p['accent']};
        color: #ffffff;
        border: none;
        border-radius: 10px;
        padding: 9px 18px;
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {p['accent_hover']};
    }}
    QPushButton#PrimaryButton:disabled {{
        background-color: {p['border']};
        color: {p['text_muted']};
    }}
    QPushButton#GhostButton {{
        background-color: {p['input']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 9px;
        padding: 7px 13px;
        font-weight: 500;
    }}
    QPushButton#GhostButton:hover {{
        border-color: {p['border_hover']};
        background-color: {p['accent_soft']};
    }}
    QPushButton#GhostButton:disabled {{
        color: {p['text_muted']};
    }}
    QPushButton#DangerButton {{
        background-color: {p['danger_bg']};
        color: {p['danger']};
        border: 1px solid {p['danger']};
        border-radius: 9px;
        padding: 7px 13px;
        font-weight: 600;
    }}
    QPushButton#DangerButton:hover {{
        background-color: {p['danger']};
        color: #ffffff;
    }}
    QPushButton#FilterChip {{
        background-color: transparent;
        color: {p['text_secondary']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 5px 12px;
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton#FilterChip:checked {{
        background-color: {p['accent_soft']};
        border-color: {p['accent']};
        color: {p['accent_text']};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background-color: {p['input']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 8px 12px;
        selection-background-color: {p['accent']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {p['accent']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p['card']};
        color: {p['text']};
        border: 1px solid {p['border']};
        selection-background-color: {p['accent_soft']};
    }}
    QListWidget {{
        background-color: {p['input']};
        border: 1px solid {p['border']};
        border-radius: 10px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        border-radius: 8px;
        padding: 8px 10px;
        margin: 2px 0px;
        color: {p['text']};
    }}
    QListWidget::item:selected {{
        background-color: {p['accent_soft']};
        border: 1px solid {p['accent']};
        color: {p['text']};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {p['card']};
    }}
    QProgressBar {{
        background-color: {p['input']};
        border: 1px solid {p['border']};
        border-radius: 5px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent']}, stop:1 #8b5cf6);
    }}
    QScrollArea {{
        border: none;
        background-color: transparent;
    }}
    QWidget#ScrollContent {{
        background-color: transparent;
    }}
    QScrollBar:vertical {{
        background: {p['scroll_track']};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {p['scroll_thumb']};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p['accent']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QCheckBox {{
        spacing: 8px;
        color: {p['text']};
    }}
    QLabel#BadgeInfo {{
        background-color: {p['accent_soft']};
        color: {p['accent_text']};
        border: 1px solid {p['accent']};
        border-radius: 10px;
        padding: 2px 9px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeSuccess {{
        background-color: {p['success_bg']};
        color: {p['success']};
        border: 1px solid {p['success']};
        border-radius: 10px;
        padding: 2px 9px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeWarning {{
        background-color: {p['warning_bg']};
        color: {p['warning']};
        border: 1px solid {p['warning']};
        border-radius: 10px;
        padding: 2px 9px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeDanger {{
        background-color: {p['danger_bg']};
        color: {p['danger']};
        border: 1px solid {p['danger']};
        border-radius: 10px;
        padding: 2px 9px;
        font-size: 11px;
        font-weight: 600;
    }}
    """
