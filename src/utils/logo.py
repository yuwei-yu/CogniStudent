from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

LOGO_PATH = Path(__file__).resolve().parents[2] / "resources" / "xut_logo.png"


class LogoLabel(QLabel):
    def __init__(self, size: int = 64) -> None:
        super().__init__()
        self.logo_size = size
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setObjectName("xutLogo")
        self.render_logo()

    def render_logo(self) -> None:
        pixmap = QPixmap(str(LOGO_PATH))
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
