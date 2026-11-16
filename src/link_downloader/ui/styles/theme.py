"""Light Neumorphic (Soft UI) design system, QSS themes, and crisp vector icons."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from link_downloader.core.enums import ThemeMode

_ICON_PATHS: dict[str, str] = {
    "brand_logo": (
        '<path d="M8.5 9.5a3.5 3.5 0 0 1 7 0" stroke="{c}" stroke-width="2.1" '
        'stroke-linecap="round" fill="none"/>'
        '<path d="M12 8v7.5m0 0-3.2-3.2M12 15.5l3.2-3.2" stroke="{c}" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        '<path d="M6.5 18.5h11" stroke="{c}" stroke-width="2.1" stroke-linecap="round"/>'
    ),
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
    "bolt": (
        '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" stroke="{c}" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
    ),
    "sliders": (
        '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" '
        'stroke="{c}" stroke-width="2" stroke-linecap="round"/>'
    ),
}


def make_icon(name: str, color: str = "#475569", size: int = 20) -> QIcon:
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
    """Return Light Neumorphic color tokens (Soft Porcelain default or Warm Pearl variant)."""
    is_pearl = str(mode).lower() == ThemeMode.DARK.value
    if is_pearl:
        return {
            "bg": "#eef0f5",
            "sidebar": "#e6e9f1",
            "card": "#eef0f5",
            "raised_tl": "#f9fbff",
            "raised_br": "#e2e6ef",
            "inset_tl": "#dce1ec",
            "inset_br": "#f4f6fb",
            "bevel_light": "#ffffff",
            "bevel_dark": "#c5cddc",
            "input": "#e6ebf3",
            "surface_subtle": "#e8ecf4",
            "border": "#d0d7e3",
            "border_hover": "#b8c3d6",
            "text": "#1e293b",
            "text_secondary": "#475569",
            "text_muted": "#64748b",
            "accent": "#3b82f6",
            "accent_top": "#60a5fa",
            "accent_hover": "#2563eb",
            "accent_soft": "#e0e9fb",
            "accent_text": "#1d4ed8",
            "success": "#059669",
            "success_bg": "#daf5ea",
            "warning": "#d97706",
            "warning_bg": "#fef3dc",
            "danger": "#dc2626",
            "danger_bg": "#fde4e4",
            "scroll_track": "#e6e9f1",
            "scroll_thumb": "#c3ccdc",
            "icon": "#475569",
        }
    return {
        "bg": "#e8eef6",
        "sidebar": "#e3eaf4",
        "card": "#eaeff7",
        "raised_tl": "#f6f9fe",
        "raised_br": "#dee6f2",
        "inset_tl": "#d7e0ed",
        "inset_br": "#f2f6fc",
        "bevel_light": "#ffffff",
        "bevel_dark": "#c1cde0",
        "input": "#e2e9f4",
        "surface_subtle": "#e5ecf5",
        "border": "#cdd7e6",
        "border_hover": "#b3c2d8",
        "text": "#1e293b",
        "text_secondary": "#475569",
        "text_muted": "#64748b",
        "accent": "#2563eb",
        "accent_top": "#4f86f7",
        "accent_hover": "#1d4ed8",
        "accent_soft": "#dbe7fb",
        "accent_text": "#1d4ed8",
        "success": "#059669",
        "success_bg": "#d7f4e8",
        "warning": "#d97706",
        "warning_bg": "#fdf0d5",
        "danger": "#dc2626",
        "danger_bg": "#fce2e2",
        "scroll_track": "#e3eaf4",
        "scroll_thumb": "#bcc9dc",
        "icon": "#475569",
    }


def build_stylesheet(mode: ThemeMode | str) -> str:
    """Generate the tactile Light Neumorphic (Soft UI) Qt Style Sheet."""
    p = get_theme_palette(mode)
    return f"""
    QMainWindow, QDialog {{
        background-color: {p['bg']};
        color: {p['text']};
    }}
    QWidget {{
        color: {p['text']};
        font-family: "Inter", "SF Pro Text", "Segoe UI", "Noto Sans", system-ui, sans-serif;
        font-size: 13px;
    }}
    QWidget#Sidebar {{
        background-color: {p['sidebar']};
        border-right: 1px solid {p['border']};
    }}
    QFrame#Toolbar {{
        background-color: {p['sidebar']};
        border-bottom: 1px solid {p['border']};
    }}
    QFrame#Card, QGroupBox#Card {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['bevel_dark']};
        border-right-color: {p['bevel_dark']};
        border-radius: 14px;
    }}
    QFrame#EmptyCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        border-radius: 14px;
    }}
    QFrame#BannerWarning {{
        background-color: {p['warning_bg']};
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['warning']};
        border-right-color: {p['warning']};
        border-radius: 12px;
    }}
    QFrame#SubCard {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        border-radius: 10px;
    }}
    QFrame#SettingRow {{
        background-color: transparent;
        border: none;
        border-bottom: 1px solid {p['border']};
    }}
    QFrame#StatusBox {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['bevel_dark']};
        border-right-color: {p['bevel_dark']};
        border-radius: 12px;
    }}
    QLabel#PageTitle {{
        font-size: 17px;
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
        font-weight: 600;
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
        padding: 8px 12px;
        text-align: left;
        font-weight: 500;
        color: {p['text_secondary']};
    }}
    QPushButton#NavButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['bevel_dark']};
        border-right-color: {p['bevel_dark']};
        color: {p['text']};
    }}
    QPushButton#NavButton:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        color: {p['accent_text']};
        font-weight: 700;
    }}
    QPushButton#PrimaryButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {p['accent_top']}, stop:1 {p['accent']});
        color: #ffffff;
        border-style: solid;
        border-width: 1px;
        border-top-color: #93c5fd;
        border-left-color: #7fb4fc;
        border-bottom-color: {p['accent_hover']};
        border-right-color: {p['accent_hover']};
        border-radius: 10px;
        padding: 7px 15px;
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {p['accent']}, stop:1 {p['accent_hover']});
    }}
    QPushButton#PrimaryButton:pressed {{
        background-color: {p['accent_hover']};
    }}
    QPushButton#PrimaryButton:disabled {{
        background: {p['inset_tl']};
        border-color: {p['border']};
        color: {p['text_muted']};
    }}
    QPushButton#GhostButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        color: {p['text']};
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['bevel_dark']};
        border-right-color: {p['bevel_dark']};
        border-radius: 10px;
        padding: 6px 12px;
        font-weight: 500;
    }}
    QPushButton#GhostButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #ffffff, stop:1 {p['raised_tl']});
        color: {p['accent_text']};
    }}
    QPushButton#GhostButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
    }}
    QPushButton#GhostButton:disabled {{
        color: {p['text_muted']};
        background: {p['surface_subtle']};
    }}
    QPushButton#IconButton {{
        background-color: transparent;
        color: {p['text_secondary']};
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 4px 6px;
    }}
    QPushButton#IconButton:hover {{
        background-color: {p['inset_tl']};
        border-color: {p['border']};
        color: {p['text']};
    }}
    QPushButton#DangerButton {{
        background-color: {p['danger_bg']};
        color: {p['danger']};
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['danger']};
        border-right-color: {p['danger']};
        border-radius: 10px;
        padding: 6px 12px;
        font-weight: 600;
    }}
    QPushButton#DangerButton:hover {{
        background-color: {p['danger']};
        color: #ffffff;
    }}
    QPushButton#FilterChip {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        color: {p['text_secondary']};
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['bevel_dark']};
        border-right-color: {p['bevel_dark']};
        border-radius: 9px;
        padding: 5px 11px;
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton#FilterChip:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        color: {p['accent_text']};
        font-weight: 700;
    }}
    QLineEdit, QComboBox, QSpinBox {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        color: {p['text']};
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        border-radius: 10px;
        padding: 6px 11px;
        min-height: 20px;
        selection-background-color: {p['accent']};
        selection-color: #ffffff;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {p['accent']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p['raised_tl']};
        color: {p['text']};
        border: 1px solid {p['border']};
        border-radius: 8px;
        selection-background-color: {p['accent_soft']};
        selection-color: {p['accent_text']};
    }}
    QListWidget {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        border-radius: 10px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        border-radius: 8px;
        padding: 6px 10px;
        margin: 2px 0px;
        color: {p['text']};
    }}
    QListWidget::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['raised_tl']}, stop:1 {p['raised_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_light']};
        border-left-color: {p['bevel_light']};
        border-bottom-color: {p['accent']};
        border-right-color: {p['accent']};
        color: {p['accent_text']};
        font-weight: 600;
    }}
    QListWidget::item:hover:!selected {{
        background-color: {p['raised_tl']};
    }}
    QProgressBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p['inset_tl']}, stop:1 {p['inset_br']});
        border-style: solid;
        border-width: 1px;
        border-top-color: {p['bevel_dark']};
        border-left-color: {p['bevel_dark']};
        border-bottom-color: {p['bevel_light']};
        border-right-color: {p['bevel_light']};
        border-radius: 4px;
        height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {p['accent']}, stop:1 #38bdf8);
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
        border: 1px solid {p['border']};
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeSuccess {{
        background-color: {p['success_bg']};
        color: {p['success']};
        border: 1px solid {p['success']};
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeWarning {{
        background-color: {p['warning_bg']};
        color: {p['warning']};
        border: 1px solid {p['warning']};
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    QLabel#BadgeDanger {{
        background-color: {p['danger_bg']};
        color: {p['danger']};
        border: 1px solid {p['danger']};
        border-radius: 8px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    """
