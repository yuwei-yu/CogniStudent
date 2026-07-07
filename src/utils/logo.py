from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

from utils.helpers import bundled_root, resources_root

LOGO_NAME = "xut_logo.png"


def logo_path() -> Path:
    visible_path = resources_root() / LOGO_NAME
    if visible_path.exists():
        return visible_path
    return bundled_root() / "resources" / LOGO_NAME


class LogoLabel(QLabel):
    def __init__(self, size: int = 64) -> None:
        super().__init__()
        self.logo_size = size
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setObjectName("xutLogo")
        self.render_logo()

    def render_logo(self) -> None:
        pixmap = QPixmap(str(logo_path()))
        if pixmap.isNull():
            self.setText("XUT")
            self.setStyleSheet(
                "font-size: 14px; font-weight: 700; border: 1px solid #d7dde2; border-radius: 6px;"
            )
            return
        self.setPixmap(
            pixmap.scaled(
                self.logo_size,
                self.logo_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


def logo_label(size: int = 64) -> LogoLabel:
    return LogoLabel(size)
