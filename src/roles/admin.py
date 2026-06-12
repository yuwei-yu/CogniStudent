from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game import data_manager


class AdminWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CogniStudent - 管理员")
        self.current_activity: Optional[str] = data_manager.get_current_activity()
        self.activity_path: Optional[Path] = None
        self.resize(1040, 680)

        central = QWidget()
        root = QHBoxLayout(central)
        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("活动列表"))
        self.activity_list = QListWidget()
        self.activity_list.currentTextChanged.connect(self.select_activity)
        left_layout.addWidget(self.activity_list)
        create_button = QPushButton("新建活动")
        delete_button = QPushButton("删除活动")
        create_button.clicked.connect(self.create_activity)
        delete_button.clicked.connect(self.delete_activity)
        left_layout.addWidget(create_button)
        left_layout.addWidget(delete_button)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.title = QLabel("未选择活动")
        self.title.setObjectName("titleLabel")
        right_layout.addWidget(self.title)

        toolbar = QHBoxLayout()
        for text, slot in (
            ("上传资料压缩包", self.upload_zip),
            ("下载上传模板", self.download_template),
            ("保存参赛名单", self.save_contest),
            ("删除辅导员", self.delete_counselor),
            ("刷新", self.refresh_counselors),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        right_layout.addLayout(toolbar)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["参赛", "姓名", "工号", "学生数", "Excel", "照片文件夹"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right_layout.addWidget(self.table)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(central)
        self.refresh_activities()

    def refresh_activities(self) -> None:
        self.activity_list.clear()
        activities = data_manager.get_activities()
        self.activity_list.addItems(activities)
        if self.current_activity in activities:
            self.activity_list.setCurrentRow(activities.index(self.current_activity))
        elif activities:
            self.activity_list.setCurrentRow(0)
        else:
            self.title.setText("请先创建活动")
            self.table.setRowCount(0)

    def select_activity(self, name: str) -> None:
        if not name:
            return
        self.current_activity = name
        data_manager.set_current_activity(name)
        self.activity_path = data_manager.activity_path(name)
        self.title.setText(f"当前活动：{name}")
        self.refresh_counselors()

    def create_activity(self) -> None:
        name, ok = QInputDialog.getText(self, "新建活动", "活动名称")
        if not ok:
            return
        try:
            data_manager.create_activity(name)
        except Exception as exc:
            QMessageBox.warning(self, "创建失败", str(exc))
            return
        self.current_activity = name.strip()
        self.refresh_activities()

    def delete_activity(self) -> None:
        name = self.activity_list.currentItem().text() if self.activity_list.currentItem() else ""
        if not name:
            return
        if QMessageBox.question(self, "确认删除", f"确定删除活动“{name}”及其全部数据？") != QMessageBox.Yes:
            return
        data_manager.delete_activity(name)
        self.current_activity = None
        self.refresh_activities()

    def refresh_counselors(self) -> None:
        if not self.activity_path:
            return
        counselors = data_manager.get_counselors(self.activity_path)
        contest_ids = set(data_manager.get_contest_counselors(self.activity_path))
        self.table.setRowCount(len(counselors))
        for row, counselor in enumerate(counselors):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setCheckState(Qt.Checked if counselor.id in contest_ids else Qt.Unchecked)
            check_item.setData(Qt.UserRole, counselor.id)
            self.table.setItem(row, 0, check_item)
            try:
                students = data_manager.load_students(counselor.excel_path, counselor.photos_dir)
                count = str(len(students))
            except Exception as exc:
                count = f"读取失败：{exc}"
            values = [counselor.name, counselor.employee_id, count, counselor.excel_path.name, counselor.photos_dir.name]
            for col, value in enumerate(values, start=1):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, counselor.id)
                self.table.setItem(row, col, item)

    def upload_zip(self) -> None:
        if not self.activity_path:
            QMessageBox.warning(self, "未选择活动", "请先选择或创建活动。")
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
        text = (
            f"导入：{len(report['imported'])}；跳过：{len(report['skipped'])}；"
            f"警告：{len(report['warnings'])}；错误：{len(report['errors'])}"
        )
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

    def save_contest(self) -> None:
        if not self.activity_path:
            return
        selected: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                selected.append(str(item.data(Qt.UserRole)))
        data_manager.save_contest_counselors(self.activity_path, selected)
        QMessageBox.information(self, "已保存", f"已保存 {len(selected)} 名参赛辅导员。")

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
