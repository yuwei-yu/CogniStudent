from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QMessageBox
from qt_material import apply_stylesheet

from game import data_manager
from roles.admin import AdminWindow
from roles.counselor import CounselorWindow
from roles.judge import JudgeWindow
from roles.login import ActivityDialog, AdminLoginDialog, CounselorLoginDialog, JudgeLoginDialog, RoleDialog


def choose_activity() -> Optional[str]:
    dialog = ActivityDialog()
    if dialog.exec() != dialog.Accepted:
        return None
    return dialog.activity_name


def main() -> int:
    data_manager.bootstrap()
    app = QApplication(sys.argv)
    apply_stylesheet(app, theme="dark_teal.xml", extra={
        "font_family": "Microsoft YaHei",
        "density_scale": "-1",
    })
    app.setStyleSheet(app.styleSheet() + "\n#titleLabel { font-size: 20px; font-weight: 600; }\n")

    if not data_manager.get_activities():
        QMessageBox.information(None, "暂无活动", "resources 下暂无活动，请以管理员身份创建活动。")

    role_dialog = RoleDialog()
    if role_dialog.exec() != role_dialog.Accepted or not role_dialog.selected_role:
        return 0

    window = None
    if role_dialog.selected_role == "admin":
        login = AdminLoginDialog()
        if login.exec() != login.Accepted:
            return 0
        window = AdminWindow()
    elif role_dialog.selected_role == "counselor":
        activity_name = choose_activity()
        if not activity_name:
            return 0
        path = data_manager.activity_path(activity_name)
        login = CounselorLoginDialog(path)
        if login.exec() != login.Accepted or not login.counselor:
            return 0
        window = CounselorWindow(path, login.counselor)
    else:
        activity_name = choose_activity()
        if not activity_name:
            return 0
        login = JudgeLoginDialog()
        if login.exec() != login.Accepted:
            return 0
        window = JudgeWindow(data_manager.activity_path(activity_name))

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
