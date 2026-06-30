from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from utils.logo import logo_label


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
        self.page_size = 12
        self.current_page = 0
        self.current_counselors = []
        self.resize(1120, 760)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home_page = self.build_home_page()
        self.settings_page = self.build_settings_page()
        self.activity_page = self.build_activity_page()
        for page in (self.home_page, self.settings_page, self.activity_page):
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
        layout.addWidget(logo_label(88), alignment=Qt.AlignHCenter)
        title = QLabel("管理员工作台")
        title.setObjectName("titleLabel")
        layout.addWidget(title)

        actions = (
            ("比赛详情", "导入资料并逐位辅导员进入答题。", self.open_default_activity),
            ("比赛设置", "设置题目、计时、抽题数量和答题字段。", self.show_settings),
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

    def build_settings_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        top = QHBoxLayout()
        back = QPushButton("返回")
        back.clicked.connect(self.show_home)
        title = QLabel("全局比赛设置")
        title.setObjectName("titleLabel")
        top.addWidget(back)
        top.addWidget(logo_label(42))
        top.addWidget(title)
        top.addStretch(1)
        layout.addLayout(top)

        self.settings_layout = QVBoxLayout()
        layout.addLayout(self.settings_layout)
        layout.addStretch(1)
        return self.scroll_page(content)

    def build_activity_page(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        top = QHBoxLayout()
        back = QPushButton("返回")
        back.clicked.connect(self.show_home)
        self.activity_title = QLabel("比赛详情")
        self.activity_title.setObjectName("titleLabel")
        top.addWidget(back)
        top.addWidget(logo_label(42))
        top.addWidget(self.activity_title)
        top.addStretch(1)
        self.contest_count_label = QLabel("已答题：0 / 0")
        self.contest_count_label.setObjectName("titleLabel")
        top.addWidget(self.contest_count_label)
        layout.addLayout(top)

        row = QHBoxLayout()
        for group_title, actions in (
            ("资料", (
                ("上传资料", self.upload_zip),
                ("下载上传模板", self.download_template),
                ("刷新", self.refresh_counselors),
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

        filter_row = QHBoxLayout()
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["工号升序", "工号降序"])
        self.sort_combo.setMinimumWidth(120)
        self.sort_combo.currentIndexChanged.connect(lambda _=0: self.reset_page_and_refresh())
        self.unplayed_only = QCheckBox("只看未参赛")
        self.unplayed_only.stateChanged.connect(lambda _=0: self.reset_page_and_refresh())
        self.page_label = QLabel("第 1 / 1 页")
        prev_page = QPushButton("上一页")
        next_page = QPushButton("下一页")
        prev_page.clicked.connect(self.prev_page)
        next_page.clicked.connect(self.next_page)
        filter_row.addWidget(QLabel("排序"))
        filter_row.addWidget(self.sort_combo)
        filter_row.addWidget(self.unplayed_only)
        filter_row.addStretch(1)
        filter_row.addWidget(prev_page)
        filter_row.addWidget(next_page)
        filter_row.addWidget(self.page_label)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["参赛", "姓名", "工号", "学生数", "次数", "Excel"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 132)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.table)
        return self.scroll_page(content)

    def show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)

    def show_settings(self) -> None:
        self.rebuild_settings_page()
        self.stack.setCurrentWidget(self.settings_page)

    def open_default_activity(self) -> None:
        self.select_activity(data_manager.get_current_activity() or data_manager.DEFAULT_ACTIVITY_NAME)

    def select_activity(self, name: str) -> None:
        self.current_activity = name
        data_manager.set_current_activity(name)
        self.activity_path = data_manager.activity_path(name)
        self.activity_title.setText(f"比赛详情：{name}")
        self.current_page = 0
        self.refresh_counselors()
        self.stack.setCurrentWidget(self.activity_page)

    def refresh_counselors(self) -> None:
        if not self.activity_path:
            return
        counselors = data_manager.get_counselors(self.activity_path)
        attempts = data_manager.load_attempts(self.activity_path)
        if self.unplayed_only.isChecked():
            counselors = [counselor for counselor in counselors if attempts.get(counselor.id, 0) <= 0]
        reverse = self.sort_combo.currentIndex() == 1
        counselors.sort(key=lambda counselor: counselor.employee_id or counselor.id, reverse=reverse)
        self.current_counselors = counselors
        page_count = max(1, (len(counselors) + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, page_count - 1)
        start = self.current_page * self.page_size
        page_counselors = counselors[start : start + self.page_size]
        self.table.setRowCount(len(page_counselors))
        for row, counselor in enumerate(page_counselors):
            attempts_count = attempts.get(counselor.id, 0)
            values = [
                counselor.name,
                counselor.employee_id,
                self.student_count_text(counselor),
                str(attempts_count),
                counselor.excel_path.name,
            ]
            button = QPushButton("开始比赛" if attempts_count <= 0 else "再次参赛")
            button.setMinimumHeight(34)
            button.setMaximumWidth(104)
            button.clicked.connect(partial(self.start_counselor_competition, counselor))
            button_box = QWidget()
            button_layout = QHBoxLayout(button_box)
            button_layout.setContentsMargins(10, 6, 10, 6)
            button_layout.addWidget(button)
            self.table.setCellWidget(row, 0, button_box)
            self.table.setRowHeight(row, 52)
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, counselor.id)
                self.table.setItem(row, col, item)
        completed = sum(1 for count in data_manager.load_attempts(self.activity_path).values() if count > 0)
        total = len(data_manager.get_counselors(self.activity_path))
        self.update_contest_count_label(completed, total)
        self.page_label.setText(f"第 {self.current_page + 1} / {page_count} 页")

    def reset_page_and_refresh(self) -> None:
        self.current_page = 0
        self.refresh_counselors()

    def update_contest_count_label(self, contest_count: Optional[int] = None, total_count: Optional[int] = None) -> None:
        if not self.activity_path:
            self.contest_count_label.setText("已答题：0 / 0")
            return
        if contest_count is None:
            contest_count = len(data_manager.get_contest_counselors(self.activity_path))
        if total_count is None:
            total_count = len(data_manager.get_counselors(self.activity_path))
        self.contest_count_label.setText(f"已答题：{contest_count} / {total_count}")

    def prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_counselors()

    def next_page(self) -> None:
        if not self.current_counselors:
            return
        page_count = max(1, (len(self.current_counselors) + self.page_size - 1) // self.page_size)
        if self.current_page < page_count - 1:
            self.current_page += 1
            self.refresh_counselors()

    def student_count_text(self, counselor) -> str:
        try:
            return str(
                len(
                    data_manager.load_students(
                        counselor.excel_path,
                        counselor.photos_dir,
                        include_blacklisted=True,
                    )
                )
            )
        except Exception as exc:
            return f"读取失败：{exc}"

    def rebuild_settings_page(self) -> None:
        while self.settings_layout.count():
            item = self.settings_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        settings = data_manager.get_contest_settings()
        group = QGroupBox("全局比赛设置")
        group_layout = QVBoxLayout(group)
        rounds_row = QHBoxLayout()
        round_checks = {}
        for round_name in ("大海捞针", "鱼目混珠", "描述定位"):
            check = QCheckBox(round_name)
            check.setChecked(round_name in settings.get("enabled_rounds", []))
            round_checks[round_name] = check
            rounds_row.addWidget(check)
        rounds_row.addStretch(1)
        group_layout.addLayout(rounds_row)

        form = QGridLayout()
        spin_widgets = {}
        spin_defs = (
            ("needle_duration_seconds", "大海捞针时间", 30, 1800),
            ("needle_student_count", "大海捞针人数", 1, 20),
            ("mixed_duration_seconds", "鱼目混珠时间", 30, 1800),
            ("mixed_own_count", "本人学生数", 1, 20),
            ("mixed_distractor_count", "干扰照片数", 0, 50),
            ("locate_duration_seconds", "描述定位时间", 30, 1800),
            ("locate_question_count", "描述定位题数", 1, 20),
        )
        for index, (key, label, minimum, maximum) in enumerate(spin_defs):
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(int(settings.get(key, data_manager.DEFAULT_CONTEST_SETTINGS[key])))
            spin.setMinimumWidth(96)
            spin_widgets[key] = spin
            form.addWidget(QLabel(label), index // 2, (index % 2) * 2)
            form.addWidget(spin, index // 2, (index % 2) * 2 + 1)
        group_layout.addLayout(form)

        fields_layout = QVBoxLayout()
        field_edits = []
        for field in settings.get("answer_fields", []):
            self.add_field_row(fields_layout, field_edits, str(field))
        add_field = QPushButton("添加字段")
        add_field.clicked.connect(lambda _=False, layout=fields_layout, edits=field_edits: self.add_field_row(layout, edits, ""))
        group_layout.addWidget(QLabel("答题字段"))
        group_layout.addLayout(fields_layout)
        group_layout.addWidget(add_field)
        save = QPushButton("保存全局设置")
        save.clicked.connect(partial(self.save_global_settings, round_checks, spin_widgets, field_edits))
        group_layout.addWidget(save)
        self.settings_layout.addWidget(group)

    def add_field_row(self, layout: QVBoxLayout, edits: list[QLineEdit], value: str) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        edit = QLineEdit(value)
        edit.setMinimumWidth(180)
        rename = QPushButton("编辑")
        remove = QPushButton("删除")
        rename.clicked.connect(lambda: edit.setFocus())
        remove.clicked.connect(lambda: (edits.remove(edit) if edit in edits else None, row.deleteLater()))
        row_layout.addWidget(edit)
        row_layout.addWidget(rename)
        row_layout.addWidget(remove)
        row_layout.addStretch(1)
        edits.append(edit)
        layout.addWidget(row)

    def save_global_settings(self, round_checks: dict, spin_widgets: dict, field_edits: list[QLineEdit]) -> None:
        enabled_rounds = [name for name, check in round_checks.items() if check.isChecked()]
        fields = [edit.text().strip() for edit in field_edits if edit.text().strip()]
        if not enabled_rounds:
            QMessageBox.warning(self, "设置无效", "至少选择一个比赛环节。")
            return
        if not fields:
            QMessageBox.warning(self, "设置无效", "至少添加一个答题字段。")
            return
        settings = {key: spin.value() for key, spin in spin_widgets.items()}
        settings["enabled_rounds"] = enabled_rounds
        settings["answer_fields"] = fields
        data_manager.save_contest_settings(settings)
        QMessageBox.information(self, "已保存", "全局比赛设置已保存。")

    def upload_zip(self) -> None:
        if not self.activity_path:
            QMessageBox.warning(self, "未进入比赛", "请先进入比赛详情。")
            return
        data_file, _ = QFileDialog.getOpenFileName(self, "选择资料文件", "", "Excel/Zip files (*.xlsx *.zip)")
        if not data_file:
            return
        if QMessageBox.question(self, "确认覆盖", "上传新资料会删除当前比赛已导入的所有辅导员资料、答题次数和成绩，然后使用本次资料重新导入。是否继续？") != QMessageBox.Yes:
            return
        try:
            path = Path(data_file)
            if path.suffix.lower() == ".zip":
                report = data_manager.upload_zip(path, self.activity_path, overwrite=True, replace_existing=True)
            else:
                report = data_manager.upload_excel(path, self.activity_path, overwrite=True, replace_existing=True)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.refresh_counselors()
        text = f"导入：{len(report['imported'])}；跳过：{len(report['skipped'])}；警告：{len(report['warnings'])}；错误：{len(report['errors'])}"
        details = "\n".join(report["warnings"] + report["errors"])
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

    def start_counselor_competition(self, counselor) -> None:
        if not self.activity_path:
            QMessageBox.warning(self, "未进入比赛", "请先进入比赛详情。")
            return
        self.competition_window = CompetitionControlWindow(
            self.activity_path,
            counselor,
            finish_callback=self.refresh_counselors,
        )
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
