from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from utils.helpers import read_json, resources_root, write_json


THEME_CONFIG = "ui_config.json"
THEMES = {
    "dark": {"label": "黑夜", "qt_material": "dark_teal.xml"},
    "light": {"label": "白天", "qt_material": "light_teal.xml"},
}


def preferred_font_family() -> str:
    if sys.platform == "darwin":
        return "PingFang SC"
    if sys.platform.startswith("win"):
        return "Microsoft YaHei"
    return "Noto Sans CJK SC"


def theme_config_path():
    return resources_root() / THEME_CONFIG


def current_theme() -> str:
    data = read_json(theme_config_path(), {"theme": "dark"})
    theme = data.get("theme")
    return theme if theme in THEMES else "dark"


def save_theme(theme: str) -> None:
    write_json(theme_config_path(), {"theme": theme if theme in THEMES else "dark"})


def toggle_theme() -> str:
    theme = "light" if current_theme() == "dark" else "dark"
    save_theme(theme)
    apply_current_theme()
    return theme


def apply_current_theme() -> None:
    app = QApplication.instance()
    if app is None:
        return
    theme = current_theme()
    apply_stylesheet(
        app,
        theme=THEMES[theme]["qt_material"],
        extra={
            "font_family": preferred_font_family(),
            "density_scale": "-1",
        },
    )
    app.setStyleSheet(app.styleSheet() + common_qss(theme))


def current_theme_label() -> str:
    return THEMES[current_theme()]["label"]


def common_qss(theme: str) -> str:
    if theme == "light":
        panel = "#ffffff"
        border = "#d7e1df"
        table = "#f8fbfa"
        text = "#1f2d2f"
        muted_text = "#31484c"
        button_text = "#123236"
        button_bg = "#f5faf9"
        button_border = "#6f9fa3"
        button_hover = "#e6f2f1"
        button_pressed = "#d2e6e4"
        disabled_text = "#8a9a9d"
    else:
        panel = "#263238"
        border = "#455a64"
        table = "#1f2a30"
        text = "#eef6f5"
        muted_text = "#d9eeee"
        button_text = "#eef6f5"
        button_bg = "#2f3f46"
        button_border = "#607d8b"
        button_hover = "#38515a"
        button_pressed = "#263940"
        disabled_text = "#8ea1a7"
    return f"""
    QWidget {{
        color: {text};
    }}
    #titleLabel {{
        font-size: 20px;
        font-weight: 600;
        color: {muted_text};
    }}
    QLabel, QCheckBox, QRadioButton {{
        color: {text};
    }}
    QGroupBox {{
        border: 1px solid {border};
        border-radius: 6px;
        margin-top: 12px;
        padding: 10px;
        background: {panel};
        color: {text};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        font-weight: 600;
        color: {muted_text};
    }}
    QTableWidget {{
        gridline-color: {border};
        background: {table};
        alternate-background-color: {panel};
        color: {text};
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        color: {text};
    }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget {{
        color: {text};
        background: {panel};
    }}
    QPushButton {{
        min-height: 28px;
        border-radius: 4px;
        color: {button_text};
        background: {button_bg};
        border: 1px solid {button_border};
        padding: 4px 10px;
    }}
    QPushButton:hover {{
        background: {button_hover};
        border: 1px solid {muted_text};
    }}
    QPushButton:pressed {{
        background: {button_pressed};
        border: 1px solid {muted_text};
    }}
    QPushButton:disabled {{
        color: {disabled_text};
        border: 1px solid {border};
    }}
    """
