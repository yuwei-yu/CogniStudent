from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

from game import data_manager
from roles.admin import AdminWindow
from roles.login import AdminLoginDialog
from utils import theme


class AppController:
    def __init__(self) -> None:
        self.window: Optional[QMainWindow] = None

    def toggle_theme(self) -> None:
        theme.toggle_theme()

    def show_login(self) -> None:
        login = AdminLoginDialog(theme_callback=self.toggle_theme)
        if login.exec() != QDialog.Accepted:
            if self.window is None:
                QApplication.instance().quit()
            return
        if QMessageBox.question(None, "导入历史数据", "是否先导入历史数据 zip？") == QMessageBox.Yes:
            self.import_data_package("导入历史数据")
        self.window = AdminWindow(logout_callback=self.logout, theme_callback=self.toggle_theme)
        self.window.show()

    def import_data_package(self, title: str) -> bool:
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog

        zip_file, _ = QFileDialog.getOpenFileName(None, title, "", "Zip files (*.zip)")
        if not zip_file:
            return False
        try:
            report = data_manager.import_data_package(Path(zip_file), overwrite=True)
        except Exception as exc:
            QMessageBox.critical(None, "导入失败", str(exc))
            return False
        QMessageBox.information(None, "导入完成", f"已导入 {len(report['imported'])} 个文件。")
        return True

    def logout(self) -> None:
        old_window = self.window
        self.window = None
        if old_window:
            old_window.hide()
            old_window.deleteLater()
        QTimer.singleShot(0, self.show_login)


def main() -> int:
    data_manager.bootstrap()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    theme.apply_current_theme()

    controller = AppController()
    QTimer.singleShot(0, controller.show_login)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
