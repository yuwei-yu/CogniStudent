from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from game import data_manager
from utils import theme


class RoleDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, theme_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择角色")
        self.selected_role: Optional[str] = None
        self.theme_callback = theme_callback
        layout = QVBoxLayout(self)
        title = QLabel("辅导员辨识学生系统")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        layout.addWidget(theme_button)
        row = QHBoxLayout()
        for text, role in (("管理员", "admin"), ("辅导员", "counselor"), ("评委", "judge")):
            button = QPushButton(text)
            button.setMinimumHeight(48)
            button.clicked.connect(lambda _=False, r=role: self.choose(r))
            row.addWidget(button)
        layout.addLayout(row)
        self.resize(420, 160)

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")

    def choose(self, role: str) -> None:
        self.selected_role = role
        self.accept()


class ActivityDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择活动")
        self.activity_name: Optional[str] = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("请选择当前活动"))
        self.combo = QComboBox()
        self.combo.addItems(data_manager.get_activities())
        layout.addWidget(self.combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_activity)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(360, 120)

    def accept_activity(self) -> None:
        self.activity_name = self.combo.currentText()
        if not self.activity_name:
            QMessageBox.warning(self, "无活动", "请先由管理员创建活动。")
            return
        data_manager.set_current_activity(self.activity_name)
        self.accept()


class AdminLoginDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, theme_callback: Optional[Callable[[], None]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("管理员登录")
        self.theme_callback = theme_callback
        layout = QFormLayout(self)
        self.username = QLineEdit("admin")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        layout.addRow("账号", self.username)
        layout.addRow("密码", self.password)
        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        layout.addWidget(theme_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.try_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def try_login(self) -> None:
        if data_manager.authenticate_admin(self.username.text(), self.password.text()):
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败", "管理员账号或密码错误。")

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")


class CounselorLoginDialog(QDialog):
    def __init__(self, activity_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("辅导员登录")
        self.activity_path = activity_path
        self.counselor = None
        layout = QFormLayout(self)
        self.name = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        layout.addRow("姓名", self.name)
        layout.addRow("工号", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.try_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def try_login(self) -> None:
        counselor = data_manager.authenticate_counselor(self.activity_path, self.name.text(), self.password.text())
        if counselor:
            self.counselor = counselor
            self.accept()
        else:
            QMessageBox.warning(self, "登录失败", "未找到匹配的姓名和工号。")


class JudgeLoginDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("评委登录")
        layout = QFormLayout(self)
        self.username = QLineEdit("judge")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        layout.addRow("账号", self.username)
        layout.addRow("密码", self.password)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.try_login)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def try_login(self) -> None:
        QMessageBox.information(self, "功能已调整", "当前版本使用管理员登录后启动单机双屏比赛，不再提供评委登录。")
