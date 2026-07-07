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
        page = "#f6f8fb"
        border = "#e5e8ee"
        table = "#ffffff"
        header = "#f7f8fa"
        text = "#202833"
        muted_text = "#5b6573"
        button_text = "#1f3f68"
        button_bg = "#ffffff"
        button_border = "#d8dde6"
        button_hover = "#f0f5ff"
        button_pressed = "#e4ecfb"
        disabled_text = "#9aa3af"
        selection = "#2f6fed"
    else:
        panel = "#20262e"
        page = "#161b22"
        border = "#323b46"
        table = "#1b222a"
        header = "#232b35"
        text = "#eef2f7"
        muted_text = "#c8d0da"
        button_text = "#eef2f7"
        button_bg = "#242c36"
        button_border = "#3b4653"
        button_hover = "#2d3947"
        button_pressed = "#1f2731"
        disabled_text = "#8792a0"
        selection = "#2f6fed"
    return f"""
    QWidget {{
        color: {text};
        background: {page};
    }}
    #titleLabel {{
        font-size: 20px;
        font-weight: 700;
        color: {muted_text};
    }}
    QLabel, QCheckBox, QRadioButton {{
        color: {text};
    }}
    QGroupBox {{
        border: 1px solid {border};
        border-radius: 8px;
        margin-top: 14px;
        padding: 12px;
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
        alternate-background-color: {header};
        color: {text};
        border: 1px solid {border};
        border-radius: 8px;
        selection-background-color: {selection};
        selection-color: #ffffff;
    }}
    QHeaderView::section {{
        color: {text};
        background: {header};
        border: 0;
        border-right: 1px solid {border};
        border-bottom: 1px solid {border};
        padding: 7px 8px;
        font-weight: 700;
    }}
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget {{
        color: {text};
        background: {panel};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 5px 8px;
    }}
    QPushButton {{
        min-height: 30px;
        border-radius: 6px;
        color: {button_text};
        background: {button_bg};
        border: 1px solid {button_border};
        padding: 5px 12px;
        font-weight: 600;
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
