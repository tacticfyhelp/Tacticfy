"""Apple-style frosted-glass themes (Light / Dark) shared by every tab."""

from dataclasses import dataclass, field
from typing import Dict

FONT_STACK = '"SF Pro Text", "SF Pro Display", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY = "Segoe UI"  # QFont family for custom painting (SF Pro is not shipped on Windows)


@dataclass(frozen=True)
class Theme:
    """Every colour the UI uses; widgets never hard-code colours."""

    name: str
    is_dark: bool
    # Surfaces
    canvas: str
    card: str
    card_border: str
    control: str
    control_hover: str
    control_border: str
    segment_track: str
    segment_selected: str
    segment_selected_text: str
    table_alt: str
    header_bg: str
    selection: str
    selection_text: str
    # Text
    text: str
    text_secondary: str
    text_tertiary: str
    # Accents
    accent: str
    accent_hover: str
    accent_text: str
    accent_label: str  # accent used for TEXT on cards (>= 4.5:1 contrast)
    green: str
    green_hover: str
    # Pitch
    turf: str
    turf_stripe: str
    pitch_line: str
    pitch_border: str
    pitch_title: str
    node_ip: str
    node_oop: str
    node_alert: str
    node_ring: str
    label_bg: str
    label_border: str
    label_text: str
    label_ip_role: str
    label_oop_role: str
    # Semantic colours (status bar, alerts, advisor categories)
    status: Dict[str, str] = field(default_factory=dict)
    categories: Dict[str, str] = field(default_factory=dict)


LIGHT = Theme(
    name="Light",
    is_dark=False,
    canvas="#f5f5f7",
    card="rgba(255, 255, 255, 0.88)",
    card_border="rgba(0, 0, 0, 0.08)",
    control="rgba(255, 255, 255, 0.92)",
    control_hover="rgba(0, 0, 0, 0.04)",
    control_border="rgba(0, 0, 0, 0.12)",
    segment_track="rgba(118, 118, 128, 0.12)",
    segment_selected="#ffffff",
    segment_selected_text="#1d1d1f",
    table_alt="rgba(0, 0, 0, 0.025)",
    header_bg="rgba(246, 246, 248, 0.95)",
    selection="rgba(0, 122, 255, 0.14)",
    selection_text="#1d1d1f",
    text="#1d1d1f",
    text_secondary="#515154",
    text_tertiary="#6e6e73",
    accent="#007aff",
    accent_hover="#0066d6",
    accent_text="#ffffff",
    accent_label="#0062cc",
    green="#34c759",
    green_hover="#2db14f",
    turf="#1e6b43",
    turf_stripe="#22754a",
    pitch_line="rgba(255, 255, 255, 0.55)",
    pitch_border="rgba(0, 0, 0, 0.10)",
    pitch_title="#1d1d1f",
    node_ip="#007aff",
    node_oop="#0f8f86",
    node_alert="#ff3b30",
    node_ring="#ffffff",
    label_bg="rgba(255, 255, 255, 0.93)",
    label_border="rgba(0, 0, 0, 0.10)",
    label_text="#1d1d1f",
    label_ip_role="#0060df",
    label_oop_role="#0b7a72",
    status={
        "muted": "#6e6e73",
        "info": "#0060df",
        "success": "#1f8a3b",
        "warning": "#b25000",
        "error": "#d70015",
    },
    # Darker variants of Apple system colours: >= 4.5:1 contrast on white cards.
    categories={
        "core": "#1f8a3b",
        "rotation": "#4d7c0f",
        "loan": "#0060df",
        "sell_high": "#c93400",
        "offload": "#d70015",
    },
)

DARK = Theme(
    name="Dark",
    is_dark=True,
    canvas="#1c1c1e",
    card="rgba(44, 44, 46, 0.88)",
    card_border="rgba(255, 255, 255, 0.10)",
    control="rgba(58, 58, 60, 0.90)",
    control_hover="rgba(255, 255, 255, 0.08)",
    control_border="rgba(255, 255, 255, 0.14)",
    segment_track="rgba(118, 118, 128, 0.24)",
    segment_selected="#636366",
    segment_selected_text="#ffffff",
    table_alt="rgba(255, 255, 255, 0.035)",
    header_bg="rgba(58, 58, 60, 0.95)",
    selection="rgba(10, 132, 255, 0.30)",
    selection_text="#ffffff",
    text="#f5f5f7",
    text_secondary="#c7c7cc",
    text_tertiary="#8e8e93",
    accent="#0a84ff",
    accent_hover="#3395ff",
    accent_text="#ffffff",
    accent_label="#4da3ff",
    green="#30d158",
    green_hover="#4cd964",
    turf="#185a38",
    turf_stripe="#1c6440",
    pitch_line="rgba(255, 255, 255, 0.45)",
    pitch_border="rgba(255, 255, 255, 0.12)",
    pitch_title="#f5f5f7",
    node_ip="#0a84ff",
    node_oop="#30b0a8",
    node_alert="#ff453a",
    node_ring="#f5f5f7",
    label_bg="rgba(28, 28, 30, 0.88)",
    label_border="rgba(255, 255, 255, 0.14)",
    label_text="#f5f5f7",
    label_ip_role="#64d2ff",
    label_oop_role="#66d4cf",
    status={
        "muted": "#8e8e93",
        "info": "#64d2ff",
        "success": "#30d158",
        "warning": "#ffd60a",
        "error": "#ff6961",
    },
    categories={
        "core": "#30d158",
        "rotation": "#b8e986",
        "loan": "#64d2ff",
        "sell_high": "#ff9f0a",
        "offload": "#ff6961",
    },
)

THEMES = {"Light": LIGHT, "Dark": DARK}


def category_key(category: str) -> str:
    """Map a classifier category label to a theme colour key."""
    if "Core" in category:
        return "core"
    if "Rotation" in category:
        return "rotation"
    if "Loan" in category:
        return "loan"
    if "False Potential" in category:
        return "sell_high"
    return "offload"


def category_color(theme: Theme, category: str) -> str:
    return theme.categories[category_key(category)]


def build_stylesheet(t: Theme) -> str:
    """Global Qt stylesheet: frosted cards, hairline borders, segmented tabs and toggles."""
    return f"""
QMainWindow, QDialog {{
    background-color: {t.canvas};
}}
QWidget {{
    color: {t.text};
    font-family: {FONT_STACK};
    font-size: 12px;
}}
QWidget#canvas, QWidget#tabPage, QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
QLabel {{
    background: transparent;
}}

/* ---- Toolbar card ---- */
QFrame#toolbarCard, QFrame#card {{
    background-color: {t.card};
    border: 1px solid {t.card_border};
    border-radius: 10px;
}}
QLabel#toolbarLabel {{
    color: {t.text_secondary};
    font-size: 11px;
    font-weight: 500;
}}

/* ---- Buttons ---- */
QPushButton {{
    background-color: {t.control};
    color: {t.text};
    border: 1px solid {t.control_border};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {t.control_hover};
}}
QPushButton:disabled {{
    color: {t.text_tertiary};
}}
QPushButton#primaryButton {{
    background-color: {t.accent};
    color: {t.accent_text};
    border: 1px solid {t.accent};
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{
    background-color: {t.accent_hover};
}}
QPushButton#successButton {{
    background-color: {t.green};
    color: #ffffff;
    border: 1px solid {t.green};
    font-weight: 600;
}}
QPushButton#successButton:hover {{
    background-color: {t.green_hover};
}}
QPushButton#smallButton {{
    padding: 2px 9px;
    font-size: 11px;
    border-radius: 6px;
    color: {t.accent_label};
}}
QPushButton#primaryButton:disabled, QPushButton#successButton:disabled {{
    background-color: {t.segment_track};
    border-color: {t.control_border};
    color: {t.text_tertiary};
}}

/* Segmented control (Best XI / Second XI / Delta) */
QFrame#segmented {{
    background-color: {t.segment_track};
    border: none;
    border-radius: 7px;
}}
QPushButton#segment {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px 10px;
    font-size: 11px;
    color: {t.text_secondary};
}}
QPushButton#segment:hover {{
    color: {t.text};
}}
QPushButton#segment:checked {{
    background-color: {t.segment_selected};
    border: 1px solid {t.card_border};
    color: {t.segment_selected_text};
    font-weight: 600;
}}

/* ---- Inputs ---- */
QComboBox {{
    background-color: {t.control};
    color: {t.text};
    border: 1px solid {t.control_border};
    border-radius: 6px;
    padding: 3px 22px 3px 8px;
    font-size: 11px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {t.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QLineEdit {{
    background-color: {t.control};
    color: {t.text};
    border: 1px solid {t.control_border};
    border-radius: 7px;
    padding: 4px 10px;
    font-size: 12px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
}}
QLineEdit:focus {{
    border: 1px solid {t.accent};
}}
QComboBox QAbstractItemView {{
    background-color: {t.canvas};
    color: {t.text};
    border: 1px solid {t.card_border};
    border-radius: 8px;
    selection-background-color: {t.accent};
    selection-color: {t.accent_text};
    padding: 4px;
    outline: none;
}}
QCheckBox {{
    spacing: 6px;
    font-size: 11px;
    color: {t.text};
    background: transparent;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1px solid {t.control_border};
    background-color: {t.control};
}}
QCheckBox::indicator:hover {{
    border-color: {t.accent};
}}
QCheckBox::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: none;
}}

/* ---- Tabs as a segmented pill ---- */
QTabWidget::pane {{
    border: none;
    background: transparent;
    top: 2px;
}}
QTabWidget::tab-bar {{
    alignment: center;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background-color: {t.segment_track};
    color: {t.text_secondary};
    padding: 3px 14px;
    margin: 0;
    border: none;
    font-size: 11px;
    font-weight: 500;
}}
QTabBar::tab:first {{
    border-top-left-radius: 9px;
    border-bottom-left-radius: 9px;
}}
QTabBar::tab:last {{
    border-top-right-radius: 9px;
    border-bottom-right-radius: 9px;
}}
QTabBar::tab:selected {{
    background-color: {t.segment_selected};
    color: {t.segment_selected_text};
    font-weight: 600;
    border: 1px solid {t.card_border};
    border-radius: 8px;
}}
QTabBar::tab:hover:!selected {{
    color: {t.text};
}}

/* ---- Cards ---- */
QGroupBox {{
    background-color: {t.card};
    border: 1px solid {t.card_border};
    border-radius: 10px;
    margin-top: 18px;
    padding: 10px 10px 8px 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 4px;
    background: transparent;
}}

/* ---- Table ---- */
QTableWidget {{
    background-color: {t.card};
    alternate-background-color: {t.table_alt};
    color: {t.text};
    gridline-color: transparent;
    border: 1px solid {t.card_border};
    border-radius: 12px;
    selection-background-color: {t.selection};
    selection-color: {t.selection_text};
}}
QTableWidget::item {{
    padding: 4px 6px;
    border-bottom: 1px solid {t.card_border};
}}
QHeaderView {{
    background: transparent;
}}
QHeaderView::section {{
    background-color: {t.header_bg};
    color: {t.text_secondary};
    padding: 5px 6px;
    border: none;
    border-bottom: 1px solid {t.card_border};
    font-weight: 600;
    font-size: 11px;
}}
QTableCornerButton::section {{
    background-color: {t.header_bg};
    border: none;
}}

/* ---- Scrollbars (thin, macOS-like) ---- */
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    border: none;
    margin: 2px;
}}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {t.text_tertiary};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
    width: 0;
    height: 0;
}}

QToolTip {{
    background-color: {t.canvas};
    color: {t.text};
    border: 1px solid {t.card_border};
    border-radius: 6px;
    padding: 4px 8px;
}}
QMessageBox {{
    background-color: {t.canvas};
}}
"""


def to_qcolor(css: str):
    """Convert "#rrggbb" or "rgba(r, g, b, a)" (a in 0..1) into a QColor for custom painting."""
    from PySide6.QtGui import QColor

    css = css.strip()
    if css.startswith("rgba(") or css.startswith("rgb("):
        parts = [p.strip() for p in css[css.index("(") + 1:css.rindex(")")].split(",")]
        r, g, b = (int(float(v)) for v in parts[:3])
        a = float(parts[3]) if len(parts) > 3 else 1.0
        return QColor(r, g, b, max(0, min(255, round(a * 255))))
    return QColor(css)
