from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game import data_manager
from roles.competition import CompetitionControlWindow
from utils import theme


class AdminWindow(QMainWindow):
    def __init__(
        self,
        logout_callback: Optional[Callable[[], None]] = None,
        theme_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("CogniStudent - 管理员")
        self.logout_callback = logout_callback
        self.theme_callback = theme_callback
        self.current_activity: Optional[str] = data_manager.get_current_activity()
        self.activity_path: Optional[Path] = None
        self.competition_window: Optional[CompetitionControlWindow] = None
        self.resize(1120, 760)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home_page = self.build_home_page()
        self.activities_page = self.build_activities_page()
        self.settings_page = self.build_settings_page()
        self.activity_page = self.build_activity_page()
        for page in (self.home_page, self.activities_page, self.settings_page, self.activity_page):
            self.stack.addWidget(page)
        self.show_home()

    def scroll_page(self, content: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def build_home_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        title = QLabel("管理员工作台")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        actions = (
            ("活动管理", "创建、删除活动，进入活动后维护辅导员名单和参赛名单。", self.show_activities),
            ("比赛设置", "设置所有比赛统一使用的计时、抽题数量和答题字段。", self.show_settings),
            ("导入历史数据", "导入此前导出的完整历史数据 zip。", self.import_history_data),
            ("一键导出全部数据", "导出完整 resources 数据，便于换电脑恢复。", self.export_all_data),
        )
        grid = QGridLayout()
        for index, (text, description, slot) in enumerate(actions):
            group = QGroupBox(text)
            group_layout = QVBoxLayout(group)
            group_layout.addWidget(QLabel(description))
            button = QPushButton(text)
            button.clicked.connect(slot)
            group_layout.addWidget(button)
            grid.addWidget(group, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addStretch(1)
        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        layout.addWidget(theme_button)
        logout = QPushButton("退出到登录页")
        logout.clicked.connect(self.logout)
        layout.addWidget(logout)
        return self.scroll_page(content)

    def build_activities_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        top = QHBoxLayout()
        back = QPushButton("返回")
        back.clicked.connect(self.show_home)
        title = QLabel("活动列表")
        title.setObjectName("titleLabel")
        top.addWidget(back)
        top.addWidget(title)
        top.addStretch(1)
        layout.addLayout(top)

        self.activity_list = QListWidget()
        layout.addWidget(self.activity_list)
        row = QHBoxLayout()
        for text, slot in (
            ("新建活动", self.create_activity),
            ("进入活动", self.open_selected_activity),
            ("删除活动", self.delete_activity),
            ("刷新", self.refresh_activities),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        return self.scroll_page(content)

    def build_settings_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        top = QHBoxLayout()
        back = QPushButton("返回")
        back.clicked.connect(self.show_home)
        title = QLabel("全局比赛设置")
        title.setObjectName("titleLabel")
        top.addWidget(back)
        top.addWidget(title)
        top.addStretch(1)
        layout.addLayout(top)

        form_group = QGroupBox("计时与抽题")
        form_layout = QFormLayout(form_group)
        self.setting_inputs: dict[str, QSpinBox] = {}
        for key, label, minimum, maximum in (
            ("needle_duration_seconds", "大海捞针计时（秒）", 30, 1800),
            ("mixed_duration_seconds", "鱼目混珠计时（秒）", 30, 1800),
            ("locate_duration_seconds", "描述定位计时（秒）", 30, 1800),
            ("needle_student_count", "大海捞针抽取人数", 1, 20),
            ("mixed_own_count", "鱼目混珠本人学生数", 1, 20),
            ("mixed_distractor_count", "鱼目混珠干扰照片数", 0, 50),
            ("locate_question_count", "描述定位题数", 1, 20),
        ):
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            self.setting_inputs[key] = spin
            form_layout.addRow(label, spin)
        layout.addWidget(form_group)

        fields_group = QGroupBox("答题字段")
        fields_layout = QGridLayout(fields_group)
        self.answer_field_checks: dict[str, QCheckBox] = {}
        for index, field in enumerate(data_manager.DEFAULT_CONTEST_SETTINGS["answer_fields"]):
            check = QCheckBox(field)
            if field == "姓名":
                check.setChecked(True)
                check.setEnabled(False)
            self.answer_field_checks[field] = check
            fields_layout.addWidget(check, index // 4, index % 4)
        layout.addWidget(fields_group)

        save = QPushButton("保存比赛设置")
        save.clicked.connect(self.save_contest_settings)
        layout.addWidget(save)
        layout.addStretch(1)
        return self.scroll_page(content)

    def build_activity_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        top = QHBoxLayout()
        back = QPushButton("返回活动列表")
        back.clicked.connect(self.show_activities)
        self.activity_title = QLabel("活动详情")
        self.activity_title.setObjectName("titleLabel")
        top.addWidget(back)
        top.addWidget(self.activity_title)
        top.addStretch(1)
        layout.addLayout(top)

        row = QHBoxLayout()
        for group_title, actions in (
            ("资料", (
                ("上传资料压缩包", self.upload_zip),
                ("下载上传模板", self.download_template),
                ("刷新", self.refresh_counselors),
            )),
            ("参赛名单", (
                ("全部勾选", self.check_all_counselors),
                ("取消全选", self.uncheck_all_counselors),
                ("添加参赛辅导员", self.save_contest),
                ("删除辅导员", self.delete_counselor),
            )),
            ("比赛", (
                ("启动比赛", self.start_competition),
            )),
        ):
            group = QGroupBox(group_title)
            group_layout = QVBoxLayout(group)
            for text, slot in actions:
                button = QPushButton(text)
                button.clicked.connect(slot)
                group_layout.addWidget(button)
            row.addWidget(group)
        row.addStretch(1)
        layout.addLayout(row)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["参赛", "参赛状态", "姓名", "工号", "学生数", "总分", "Excel", "照片文件夹"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemChanged.connect(self.on_table_item_changed)
        layout.addWidget(self.table)
        return self.scroll_page(content)

    def show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)

    def show_activities(self) -> None:
        self.refresh_activities()
        self.stack.setCurrentWidget(self.activities_page)

    def show_settings(self) -> None:
        self.load_contest_settings()
        self.stack.setCurrentWidget(self.settings_page)

    def refresh_activities(self) -> None:
        self.activity_list.clear()
        self.activity_list.addItems(data_manager.get_activities())

    def selected_activity_name(self) -> str:
        item = self.activity_list.currentItem()
        return item.text() if item else ""

    def open_selected_activity(self) -> None:
        name = self.selected_activity_name()
        if not name:
            QMessageBox.warning(self, "未选择活动", "请先选择一个活动。")
            return
        self.select_activity(name)

    def select_activity(self, name: str) -> None:
        self.current_activity = name
        data_manager.set_current_activity(name)
        self.activity_path = data_manager.activity_path(name)
        self.activity_title.setText(f"活动详情：{name}")
        self.refresh_counselors()
        self.stack.setCurrentWidget(self.activity_page)

    def create_activity(self) -> None:
        name, ok = QInputDialog.getText(self, "新建活动", "活动名称")
        if not ok:
            return
        try:
            created_path = data_manager.create_activity(name)
        except Exception as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self.refresh_activities()
        self.select_activity(created_path.name)

    def delete_activity(self) -> None:
        name = self.selected_activity_name()
        if not name:
            QMessageBox.warning(self, "未选择活动", "请先选择要删除的活动。")
            return
        if QMessageBox.question(self, "确认删除", f"确定删除活动“{name}”及其全部数据？") != QMessageBox.Yes:
            return
        data_manager.delete_activity(name)
        if self.current_activity == name:
            self.current_activity = None
            self.activity_path = None
        self.refresh_activities()

    def refresh_counselors(self) -> None:
        if not self.activity_path:
            return
        counselors = data_manager.get_counselors(self.activity_path)
        contest_ids = set(data_manager.get_contest_counselors(self.activity_path))
        scores = data_manager.load_scores(self.activity_path)
        self.table.setRowCount(len(counselors))
        for row, counselor in enumerate(counselors):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Checked if counselor.id in contest_ids else Qt.Unchecked)
            check_item.setData(Qt.UserRole, counselor.id)
            self.table.setItem(row, 0, check_item)
            values = [
                "已参赛" if counselor.id in contest_ids else "未参赛",
                counselor.name,
                counselor.employee_id,
                self.student_count_text(counselor),
                f"{float(scores.get(counselor.id, {}).get('总分', 0)):.2f}",
                counselor.excel_path.name,
                counselor.photos_dir.name,
            ]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, counselor.id)
                self.table.setItem(row, col, item)

    def student_count_text(self, counselor) -> str:
        try:
            return str(len(data_manager.load_students(counselor.excel_path, counselor.photos_dir)))
        except Exception as exc:
            return f"读取失败：{exc}"

    def load_contest_settings(self) -> None:
        settings = data_manager.get_contest_settings()
        for key, spin in self.setting_inputs.items():
            spin.setValue(int(settings.get(key, data_manager.DEFAULT_CONTEST_SETTINGS[key])))
        fields = set(settings.get("answer_fields", data_manager.DEFAULT_CONTEST_SETTINGS["answer_fields"]))
        for field, check in self.answer_field_checks.items():
            check.setChecked(field in fields)

    def save_contest_settings(self) -> None:
        selected_fields = [field for field, check in self.answer_field_checks.items() if check.isChecked()]
        if "姓名" not in selected_fields:
            selected_fields.insert(0, "姓名")
        if len(selected_fields) < 2:
            QMessageBox.warning(self, "设置无效", "至少需要选择“姓名”以外的一个答题字段。")
            return
        settings = {key: spin.value() for key, spin in self.setting_inputs.items()}
        settings["answer_fields"] = selected_fields
        data_manager.save_contest_settings(settings)
        QMessageBox.information(self, "已保存", "全局比赛设置已保存。")

    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self.update_participation_status(item.row())

    def update_participation_status(self, row: int) -> None:
        check_item = self.table.item(row, 0)
        status_item = self.table.item(row, 1)
        if check_item and status_item:
            status_item.setText("已参赛" if check_item.checkState() == Qt.Checked else "未参赛")

    def upload_zip(self) -> None:
        if not self.activity_path:
            QMessageBox.warning(self, "未选择活动", "请先进入一个活动。")
            return
        zip_file, _ = QFileDialog.getOpenFileName(self, "选择资料压缩包", "", "Zip files (*.zip)")
        if not zip_file:
            return
        overwrite = QMessageBox.question(self, "同名处理", "如果辅导员已存在，是否覆盖？选择“否”将跳过同名数据。") == QMessageBox.Yes
        try:
            report = data_manager.upload_zip(Path(zip_file), self.activity_path, overwrite=overwrite)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.refresh_counselors()
        text = f"导入：{len(report['imported'])}；跳过：{len(report['skipped'])}；警告：{len(report['warnings'])}；错误：{len(report['errors'])}"
        details = "\n".join(report["warnings"][:30] + report["errors"][:30])
        QMessageBox.information(self, "导入完成", f"{text}\n\n{details}" if details else text)

    def download_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存上传模板", "template.zip", "Zip files (*.zip)")
        if not path:
            return
        try:
            data_manager.download_template(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))
            return
        QMessageBox.information(self, "已保存", f"模板已保存到：{path}")

    def import_history_data(self) -> None:
        zip_file, _ = QFileDialog.getOpenFileName(self, "导入历史数据", "", "Zip files (*.zip)")
        if not zip_file:
            return
        overwrite = QMessageBox.question(self, "导入方式", "是否覆盖本机已有同名数据？") == QMessageBox.Yes
        try:
            report = data_manager.import_data_package(Path(zip_file), overwrite=overwrite)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        QMessageBox.information(self, "导入完成", f"导入文件：{len(report['imported'])}；跳过：{len(report['skipped'])}")

    def export_all_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "一键导出全部数据", "CogniStudent_历史数据.zip", "Zip files (*.zip)")
        if not path:
            return
        try:
            output = data_manager.export_all_data_package(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"全部数据已导出到：{output}")

    def show_score_summary(self) -> None:
        if not self.activity_path:
            return
        scores = data_manager.load_scores(self.activity_path)
        if not scores:
            QMessageBox.information(self, "成绩数据", "当前活动暂无成绩数据。")
            return
        lines = []
        for counselor_id, values in sorted(scores.items(), key=lambda item: float(item[1].get("总分", 0)), reverse=True):
            lines.append(f"{counselor_id}：{float(values.get('总分', 0)):.2f}")
        QMessageBox.information(self, "成绩数据", "\n".join(lines))

    def save_contest(self) -> None:
        if not self.activity_path:
            return
        selected: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole)))
        data_manager.save_contest_counselors(self.activity_path, selected)
        for row in range(self.table.rowCount()):
            self.update_participation_status(row)
        QMessageBox.information(self, "已添加", f"已添加 {len(selected)} 名参赛辅导员。")

    def set_all_counselors_checked(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(state)

    def check_all_counselors(self) -> None:
        self.set_all_counselors_checked(True)

    def uncheck_all_counselors(self) -> None:
        self.set_all_counselors_checked(False)

    def selected_counselor_id(self) -> Optional[str]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return str(item.data(Qt.UserRole)) if item else None

    def delete_counselor(self) -> None:
        if not self.activity_path:
            return
        counselor_id = self.selected_counselor_id()
        if not counselor_id:
            QMessageBox.warning(self, "未选择辅导员", "请先在表格中选择辅导员。")
            return
        if QMessageBox.question(self, "确认删除", f"确定删除 {counselor_id} 的 Excel 和照片文件夹？") != QMessageBox.Yes:
            return
        for suffix in (".xls", ".xlsx"):
            excel = self.activity_path / f"{counselor_id}{suffix}"
            if excel.exists():
                excel.unlink()
        folder = self.activity_path / counselor_id
        if folder.exists():
            shutil.rmtree(folder)
        self.refresh_counselors()

    def start_competition(self) -> None:
        if not self.activity_path:
            QMessageBox.warning(self, "未选择活动", "请先进入一个活动。")
            return
        counselors = data_manager.get_counselors(self.activity_path)
        if not counselors:
            QMessageBox.warning(self, "无法开始", "当前活动暂无辅导员数据，请先导入比赛资料。")
            return
        contest_ids = data_manager.get_contest_counselors(self.activity_path)
        if not contest_ids:
            if QMessageBox.question(self, "未设置参赛名单", "尚未添加参赛辅导员，是否按当前活动全部辅导员开始？") != QMessageBox.Yes:
                return
        self.competition_window = CompetitionControlWindow(self.activity_path)
        self.competition_window.show()

    def logout(self) -> None:
        if self.competition_window:
            self.competition_window.close()
            self.competition_window = None
        if self.logout_callback:
            self.logout_callback()

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")
