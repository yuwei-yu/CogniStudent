from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.models import Counselor, Student
from game import data_manager
from game.rounds import INFO_KEYS, build_locate_questions, build_mixed_round, build_needle_round, format_student_answer
from game.scorer import score_locate, score_student_fields, total_score
from utils import theme
from utils.logo import logo_label


class PhotoLabel(QLabel):
    def __init__(self, student: Student, selectable: bool = False) -> None:
        super().__init__()
        self.student = student
        self.selectable = selectable
        self.selected = False
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(160, 190)
        self.setObjectName("photoLabel")
        self.render()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.selectable:
            self.selected = not self.selected
            self.render()
        super().mousePressEvent(event)

    def render(self) -> None:
        if self.student.photo_path and self.student.photo_path.exists():
            pixmap = QPixmap(str(self.student.photo_path))
            self.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.setText("无照片")
        self.setToolTip(f"{self.student.student_id}\n{self.student.name}")
        border = "3px solid #26a69a" if self.selected else "1px solid #607d8b"
        self.setStyleSheet(f"QLabel#photoLabel {{ border: {border}; padding: 6px; }}")


class CounselorWindow(QMainWindow):
    def __init__(
        self,
        activity_path: Path,
        counselor: Counselor,
        logout_callback: Optional[Callable[[], None]] = None,
        theme_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"CogniStudent - 辅导员：{counselor.name}")
        self.logout_callback = logout_callback
        self.theme_callback = theme_callback
        self.activity_path = activity_path
        self.counselor = counselor
        self.settings = data_manager.get_contest_settings(activity_path)
        self.answer_fields = list(self.settings["answer_fields"])
        self.students = data_manager.load_students(counselor.excel_path, counselor.photos_dir)
        self.scores: dict[str, float] = {}
        self.timer = QTimer(self)
        self.remaining = 0
        self.timer.timeout.connect(self.tick)
        self.timer_label = QLabel("")
        self.training = QCheckBox("训练模式")
        self.training.setChecked(True)
        self.resize(1180, 760)

        central = QWidget()
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        title = QLabel(f"{activity_path.name} / {counselor.base_name}")
        title.setObjectName("titleLabel")
        top.addWidget(logo_label(46))
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.training)
        top.addWidget(self.timer_label)
        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        top.addWidget(theme_button)
        logout_button = QPushButton("退出到登录页")
        logout_button.clicked.connect(self.logout)
        top.addWidget(logout_button)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.build_needle_tab()
        self.build_mixed_tab()
        self.build_locate_tab()
        self.build_score_tab()

    def start_timer(self, seconds: int) -> None:
        if self.training.isChecked():
            self.timer.stop()
            self.timer_label.setText("训练模式：不计时")
            return
        self.remaining = seconds
        self.timer.start(1000)
        self.tick()

    def tick(self) -> None:
        if self.remaining <= 0:
            self.timer.stop()
            self.timer_label.setText("时间到，已自动提交")
            current = self.tabs.currentWidget()
            button = current.findChild(QPushButton, "submitButton") if current else None
            if button:
                button.click()
            return
        minute, second = divmod(self.remaining, 60)
        self.timer_label.setText(f"剩余时间：{minute:02d}:{second:02d}")
        self.remaining -= 1

    def build_photo_grid(self, students: list[Student], selectable: bool = False) -> tuple[QWidget, list[PhotoLabel]]:
        widget = QWidget()
        grid = QGridLayout(widget)
        labels: list[PhotoLabel] = []
        for index, student in enumerate(students):
            box = QGroupBox(student.student_id)
            box_layout = QVBoxLayout(box)
            label = PhotoLabel(student, selectable=selectable)
            labels.append(label)
            box_layout.addWidget(label)
            if self.training.isChecked():
                box_layout.addWidget(QLabel(student.name))
            grid.addWidget(box, index // 5, index % 5)
        return widget, labels

    def build_answer_form(self, students: list[Student]) -> tuple[QWidget, dict[str, dict[str, QLineEdit]]]:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        answer_inputs: dict[str, dict[str, QLineEdit]] = {}
        for student in students:
            group = QGroupBox(student.student_id)
            form = QFormLayout(group)
            fields: dict[str, QLineEdit] = {}
            for key in self.answer_fields:
                edit = QLineEdit()
                fields[key] = edit
                form.addRow(key, edit)
            answer_inputs[student.student_id] = fields
            layout.addWidget(group)
        return widget, answer_inputs

    def build_needle_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        start = QPushButton("开始/重抽")
        submit = QPushButton("提交")
        submit.setObjectName("submitButton")
        controls.addWidget(start)
        controls.addWidget(submit)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.needle_area = QScrollArea()
        self.needle_area.setWidgetResizable(True)
        layout.addWidget(self.needle_area)

        self.needle_round = None
        self.needle_inputs = {}

        def start_round() -> None:
            if len(self.students) < 1:
                QMessageBox.warning(self, "学生不足", "当前辅导员没有可抽取学生。")
                return
            self.needle_round = build_needle_round(
                self.students,
                count=int(self.settings["needle_student_count"]),
                duration_seconds=int(self.settings["needle_duration_seconds"]),
            )
            content = QWidget()
            content_layout = QVBoxLayout(content)
            photos, _ = self.build_photo_grid(self.needle_round.students)
            form, self.needle_inputs = self.build_answer_form(self.needle_round.students)
            content_layout.addWidget(photos)
            content_layout.addWidget(form)
            self.needle_area.setWidget(content)
            self.start_timer(self.needle_round.duration_seconds)

        def submit_round() -> None:
            if not self.needle_round:
                return
            score = 0.0
            details = []
            each_max = self.needle_round.max_score / max(1, len(self.needle_round.students))
            for student in self.needle_round.students:
                answers = {key: edit.text() for key, edit in self.needle_inputs[student.student_id].items()}
                item_score, result = score_student_fields(student, answers, each_max, self.answer_fields)
                score += item_score
                details.append(f"{student.name}：{item_score:.2f} 分")
                if self.training.isChecked():
                    details.append(format_student_answer(student, self.answer_fields))
            self.scores["大海捞针"] = round(score, 2)
            self.update_scores()
            QMessageBox.information(self, "大海捞针得分", "\n\n".join(details) + f"\n\n合计：{score:.2f}")

        start.clicked.connect(start_round)
        submit.clicked.connect(submit_round)
        self.tabs.addTab(tab, "大海捞针")

    def build_mixed_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        start = QPushButton("开始/重抽")
        confirm = QPushButton("确认选择")
        submit = QPushButton("提交信息")
        submit.setObjectName("submitButton")
        controls.addWidget(start)
        controls.addWidget(confirm)
        controls.addWidget(submit)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.mixed_area = QScrollArea()
        self.mixed_area.setWidgetResizable(True)
        layout.addWidget(self.mixed_area)
        self.mixed_round = None
        self.mixed_labels: list[PhotoLabel] = []
        self.mixed_inputs = {}
        self.mixed_selection_score = 0.0

        def start_round() -> None:
            other_ids = [c.id for c in data_manager.get_counselors(self.activity_path) if c.id != self.counselor.id]
            contest = data_manager.get_contest_counselors(self.activity_path)
            if contest and not self.training.isChecked():
                other_ids = [cid for cid in contest if cid != self.counselor.id]
            others = data_manager.load_all_students_for_judge(self.activity_path, other_ids)
            if len(self.students) < 2 or len(others) < 1:
                QMessageBox.warning(self, "学生不足", "需要至少2名本人学生和其他辅导员学生作为干扰项。")
                return
            self.mixed_round = build_mixed_round(
                self.students,
                others,
                own_count=int(self.settings["mixed_own_count"]),
                distractor_count=int(self.settings["mixed_distractor_count"]),
                duration_seconds=int(self.settings["mixed_duration_seconds"]),
            )
            content = QWidget()
            content_layout = QVBoxLayout(content)
            photos, self.mixed_labels = self.build_photo_grid(self.mixed_round.all_students, selectable=True)
            content_layout.addWidget(photos)
            self.mixed_area.setWidget(content)
            self.mixed_selection_score = 0.0
            self.start_timer(self.mixed_round.duration_seconds)

        def confirm_selection() -> None:
            if not self.mixed_round:
                return
            selected = [label.student.student_id for label in self.mixed_labels if label.selected]
            expected = {student.student_id for student in self.mixed_round.own_students}
            if set(selected) == expected:
                self.mixed_selection_score = 8.0
                QMessageBox.information(self, "选择正确", "已选中2名本人学生，请继续填写信息。")
            else:
                self.mixed_selection_score = 0.0
                QMessageBox.warning(self, "选择错误", "鱼目混珠选人错误，本题选择部分为0分。")
            form, self.mixed_inputs = self.build_answer_form(self.mixed_round.own_students)
            self.mixed_area.widget().layout().addWidget(form)

        def submit_info() -> None:
            if not self.mixed_round:
                return
            score = self.mixed_selection_score
            details = [f"选人：{self.mixed_selection_score:.2f} 分"]
            each_max = 32.0 / max(1, len(self.mixed_round.own_students))
            for student in self.mixed_round.own_students:
                answers = {key: edit.text() for key, edit in self.mixed_inputs.get(student.student_id, {}).items()}
                item_score, _ = score_student_fields(student, answers, each_max, self.answer_fields)
                score += item_score
                details.append(f"{student.name}：{item_score:.2f} 分")
                if self.training.isChecked():
                    details.append(format_student_answer(student, self.answer_fields))
            self.scores["鱼目混珠"] = round(score, 2)
            self.update_scores()
            QMessageBox.information(self, "鱼目混珠得分", "\n\n".join(details) + f"\n\n合计：{score:.2f}")

        start.clicked.connect(start_round)
        confirm.clicked.connect(confirm_selection)
        submit.clicked.connect(submit_info)
        self.tabs.addTab(tab, "鱼目混珠")

    def build_locate_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        start = QPushButton("开始/重抽")
        submit = QPushButton("提交")
        submit.setObjectName("submitButton")
        row = QHBoxLayout()
        row.addWidget(start)
        row.addWidget(submit)
        row.addStretch(1)
        layout.addLayout(row)
        self.locate_box = QWidget()
        self.locate_layout = QVBoxLayout(self.locate_box)
        layout.addWidget(self.locate_box)
        self.locate_questions = []
        self.locate_inputs: list[QLineEdit] = []

        def start_round() -> None:
            while self.locate_layout.count():
                child = self.locate_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.locate_questions = build_locate_questions(
                self.students,
                count=int(self.settings["locate_question_count"]),
                clue_fields=self.answer_fields,
            )
            self.locate_inputs = []
            for index, question in enumerate(self.locate_questions, start=1):
                group = QGroupBox(f"描述定位 {index}")
                form = QFormLayout(group)
                for key, value in question.clues.items():
                    form.addRow(key, QLabel(value or "未填写"))
                edit = QLineEdit()
                self.locate_inputs.append(edit)
                form.addRow("学生姓名", edit)
                self.locate_layout.addWidget(group)

        def submit_round() -> None:
            score = 0.0
            details = []
            for question, edit in zip(self.locate_questions, self.locate_inputs):
                item = score_locate(question.answer, edit.text())
                score += item
                line = f"{question.answer.name}：{item:.2f} 分"
                details.append(line)
            self.scores["描述定位"] = round(score, 2)
            self.update_scores()
            QMessageBox.information(self, "描述定位得分", "\n".join(details) + f"\n\n合计：{score:.2f}")

        start.clicked.connect(start_round)
        submit.clicked.connect(submit_round)
        self.tabs.addTab(tab, "描述定位")

    def build_score_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.score_text = QTextEdit()
        self.score_text.setReadOnly(True)
        save = QPushButton("保存本地成绩")
        save.clicked.connect(self.save_score)
        export = QPushButton("导出答题结果")
        export.clicked.connect(self.export_result)
        layout.addWidget(self.score_text)
        layout.addWidget(save)
        layout.addWidget(export)
        self.tabs.addTab(tab, "成绩")
        self.update_scores()

    def update_scores(self) -> None:
        total = total_score(self.scores)
        self.scores["总分"] = total
        lines = [f"{key}：{value:.2f}" for key, value in self.scores.items()]
        self.score_text.setPlainText("\n".join(lines) if lines else "暂无成绩")

    def save_score(self) -> None:
        self.update_scores()
        data_manager.save_score(self.activity_path, self.counselor.id, self.scores)
        QMessageBox.information(self, "已保存", "成绩已保存到当前比赛的 scores.json。")

    def export_result(self) -> None:
        QMessageBox.information(self, "功能已调整", "当前版本使用单机双屏比赛流程，不再导出辅导员答题结果包。")

    def logout(self) -> None:
        self.timer.stop()
        if self.logout_callback:
            self.logout_callback()

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")
