from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.models import Counselor, Student
from game import data_manager
from game.rounds import INFO_KEYS, build_locate_questions, build_mixed_round, build_needle_round, format_student_answer
from game.scorer import total_score
from utils import theme
from utils.logo import logo_label


class JudgeWindow(QMainWindow):
    def __init__(
        self,
        activity_path: Path,
        logout_callback: Optional[Callable[[], None]] = None,
        theme_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"CogniStudent - 评委：{activity_path.name}")
        self.logout_callback = logout_callback
        self.theme_callback = theme_callback
        self.activity_path = activity_path
        self.settings = data_manager.get_contest_settings(activity_path)
        self.answer_fields = list(self.settings["answer_fields"])
        self.counselors = self.load_contest_counselors()
        self.current: Optional[Counselor] = None
        self.current_students: list[Student] = []
        self.scores: dict[str, float] = {}
        self.timer = QTimer(self)
        self.remaining = 0
        self.timer.timeout.connect(self.tick)
        self.resize(1180, 760)

        central = QWidget()
        root = QVBoxLayout(central)
        top = QHBoxLayout()
        title = QLabel(f"比赛管理：{activity_path.name}")
        title.setObjectName("titleLabel")
        self.timer_label = QLabel("计时器未启动")
        top.addWidget(logo_label(46))
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.timer_label)
        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        top.addWidget(theme_button)
        logout_button = QPushButton("退出到登录页")
        logout_button.clicked.connect(self.logout)
        top.addWidget(logout_button)
        root.addLayout(top)

        splitter = QSplitter()
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("参赛辅导员"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.select_counselor)
        left_layout.addWidget(self.list_widget)
        reload_button = QPushButton("重新加载名单")
        reload_button.clicked.connect(self.reload_contest)
        left_layout.addWidget(reload_button)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        action_row = QHBoxLayout()
        self.round_combo = QComboBox()
        self.round_combo.addItems(["大海捞针", "鱼目混珠", "描述定位"])
        for text, slot in (
            ("开始环节", self.start_round),
            ("暂停/继续", self.toggle_timer),
            ("保存当前成绩", self.save_current_score),
            ("导出成绩", self.export_scores),
            ("导出评分数据", self.export_judge_results),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            action_row.addWidget(button)
        action_row.insertWidget(0, self.round_combo)
        action_row.addStretch(1)
        right_layout.addLayout(action_row)

        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        right_layout.addWidget(self.answer_text, 2)

        score_panel = QWidget()
        score_layout = QHBoxLayout(score_panel)
        self.point_label = QLabel("当前信息点：未开始")
        correct = QPushButton("正确")
        wrong = QPushButton("错误")
        correct.clicked.connect(lambda: self.add_point(True))
        wrong.clicked.connect(lambda: self.add_point(False))
        score_layout.addWidget(self.point_label)
        score_layout.addWidget(correct)
        score_layout.addWidget(wrong)
        score_layout.addStretch(1)
        right_layout.addWidget(score_panel)

        self.score_table = QTableWidget(0, 6)
        self.score_table.setHorizontalHeaderLabels(["辅导员", "大海捞针", "鱼目混珠", "描述定位", "总分", "排名"])
        self.score_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        right_layout.addWidget(self.score_table, 1)

        awards = QWidget()
        award_layout = QHBoxLayout(awards)
        self.first = QSpinBox()
        self.second = QSpinBox()
        self.third = QSpinBox()
        for label, spin in (("一等奖", self.first), ("二等奖", self.second), ("三等奖", self.third)):
            spin.setRange(0, 99)
            award_layout.addWidget(QLabel(label))
            award_layout.addWidget(spin)
        award_layout.addStretch(1)
        right_layout.addWidget(awards)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(central)
        self.round_points: list[tuple[str, float]] = []
        self.point_index = 0
        self.populate_list()
        self.refresh_score_table()

    def load_contest_counselors(self) -> list[Counselor]:
        selected = data_manager.get_contest_counselors(self.activity_path)
        all_counselors = data_manager.get_counselors(self.activity_path)
        if not selected:
            return all_counselors
        selected_set = set(selected)
        return [c for c in all_counselors if c.id in selected_set]

    def populate_list(self) -> None:
        self.list_widget.clear()
        self.list_widget.addItems([c.id for c in self.counselors])
        if self.counselors:
            self.list_widget.setCurrentRow(0)

    def reload_contest(self) -> None:
        self.counselors = self.load_contest_counselors()
        self.populate_list()
        self.refresh_score_table()

    def select_counselor(self, row: int) -> None:
        if row < 0 or row >= len(self.counselors):
            return
        self.current = self.counselors[row]
        self.answer_fields = list(self.settings["answer_fields"])
        self.current_students = data_manager.load_students(self.current.excel_path, self.current.photos_dir)
        existing = data_manager.load_scores(self.activity_path).get(self.current.id, {})
        self.scores = {key: float(value) for key, value in existing.items() if isinstance(value, (int, float))}
        self.answer_text.setPlainText(f"当前辅导员：{self.current.id}\n学生数：{len(self.current_students)}")
        self.refresh_score_table()

    def start_timer(self, seconds: int) -> None:
        self.remaining = seconds
        self.timer.start(1000)
        self.tick()

    def tick(self) -> None:
        if self.remaining <= 0:
            self.timer.stop()
            self.timer_label.setText("时间到")
            return
        minute, second = divmod(self.remaining, 60)
        self.timer_label.setText(f"剩余时间：{minute:02d}:{second:02d}")
        self.remaining -= 1

    def toggle_timer(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
            self.timer_label.setText(self.timer_label.text() + "（暂停）")
        elif self.remaining > 0:
            self.timer.start(1000)

    def start_round(self) -> None:
        if not self.current:
            QMessageBox.warning(self, "未选择辅导员", "请先选择参赛辅导员。")
            return
        round_name = self.round_combo.currentText()
        self.round_points = []
        self.point_index = 0
        try:
            if round_name == "大海捞针":
                round_data = build_needle_round(
                    self.current_students,
                    count=int(self.settings["needle_student_count"]),
                    duration_seconds=int(self.settings["needle_duration_seconds"]),
                )
                per_point = 60.0 / max(1, len(round_data.students) * len(self.answer_fields))
                chunks = []
                for student in round_data.students:
                    chunks.append(format_student_answer(student, self.answer_fields))
                    for key in self.answer_fields:
                        self.round_points.append((f"{student.name} / {key}", per_point))
                self.answer_text.setPlainText("\n\n".join(chunks))
                self.start_timer(round_data.duration_seconds)
            elif round_name == "鱼目混珠":
                contest = data_manager.get_contest_counselors(self.activity_path) or [c.id for c in self.counselors]
                others = [cid for cid in contest if cid != self.current.id]
                other_students = data_manager.load_all_students_for_judge(self.activity_path, others)
                round_data = build_mixed_round(
                    self.current_students,
                    other_students,
                    own_count=int(self.settings["mixed_own_count"]),
                    distractor_count=int(self.settings["mixed_distractor_count"]),
                    duration_seconds=int(self.settings["mixed_duration_seconds"]),
                )
                per_point = 40.0 / max(1, 2 + len(round_data.own_students) * len(self.answer_fields))
                chunks = ["本人学生：", *[format_student_answer(s, self.answer_fields) for s in round_data.own_students]]
                chunks.append("抽取照片学号：" + "、".join(s.student_id for s in round_data.all_students))
                self.round_points.extend([("选中本人学生1", per_point), ("选中本人学生2", per_point)])
                for student in round_data.own_students:
                    for key in self.answer_fields:
                        self.round_points.append((f"{student.name} / {key}", per_point))
                self.answer_text.setPlainText("\n\n".join(chunks))
                self.start_timer(round_data.duration_seconds)
            else:
                questions = build_locate_questions(
                    self.current_students,
                    count=int(self.settings["locate_question_count"]),
                    clue_fields=self.answer_fields,
                )
                chunks = []
                for index, question in enumerate(questions, start=1):
                    clues = "\n".join(f"{key}：{value or '未填写'}" for key, value in question.clues.items())
                    chunks.append(f"题 {index}\n{clues}\n答案：{question.answer.name}")
                    self.round_points.append((f"描述定位 {index}：{question.answer.name}", 10.0))
                self.answer_text.setPlainText("\n\n".join(chunks))
                self.start_timer(int(self.settings["locate_duration_seconds"]))
        except Exception as exc:
            QMessageBox.warning(self, "启动失败", str(exc))
            return
        self.scores[round_name] = 0.0
        self.update_point_label()

    def update_point_label(self) -> None:
        if self.point_index >= len(self.round_points):
            self.point_label.setText("当前信息点：已完成")
            return
        label, value = self.round_points[self.point_index]
        self.point_label.setText(f"当前信息点：{label}（{value:.2f}分）")

    def add_point(self, correct: bool) -> None:
        round_name = self.round_combo.currentText()
        if self.point_index >= len(self.round_points):
            return
        if round_name == "鱼目混珠" and self.point_index == 0 and not correct:
            self.scores[round_name] = 0.0
            self.point_index = len(self.round_points)
            self.scores["总分"] = total_score(self.scores)
            self.refresh_score_table()
            self.update_point_label()
            QMessageBox.information(self, "判定结果", "选人错误，鱼目混珠本题直接记 0 分。")
            return
        _, value = self.round_points[self.point_index]
        if correct:
            self.scores[round_name] = round(float(self.scores.get(round_name, 0.0)) + value, 2)
        self.point_index += 1
        self.scores["总分"] = total_score(self.scores)
        self.refresh_score_table()
        self.update_point_label()

    def save_current_score(self) -> None:
        if not self.current:
            return
        self.scores["总分"] = total_score(self.scores)
        data_manager.save_score(self.activity_path, self.current.id, self.scores)
        self.refresh_score_table()
        QMessageBox.information(self, "已保存", f"{self.current.id} 成绩已保存。")

    def refresh_score_table(self) -> None:
        scores = data_manager.load_scores(self.activity_path)
        if self.current:
            scores[self.current.id] = self.scores
        ranked = sorted(scores.items(), key=lambda item: float(item[1].get("总分", 0)), reverse=True)
        self.score_table.setRowCount(len(ranked))
        for row, (counselor_id, values) in enumerate(ranked):
            columns = [
                counselor_id,
                f"{float(values.get('大海捞针', 0)):.2f}",
                f"{float(values.get('鱼目混珠', 0)):.2f}",
                f"{float(values.get('描述定位', 0)):.2f}",
                f"{float(values.get('总分', 0)):.2f}",
                str(row + 1),
            ]
            for col, value in enumerate(columns):
                self.score_table.setItem(row, col, QTableWidgetItem(value))

    def export_scores(self) -> None:
        awards = {"一等奖": self.first.value(), "二等奖": self.second.value(), "三等奖": self.third.value()}
        try:
            output = data_manager.export_scores(self.activity_path, awards)
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"成绩已导出到：{output}")

    def export_judge_results(self) -> None:
        QMessageBox.information(self, "功能已调整", "当前版本使用单机双屏比赛流程，不再导出评委评分数据包。")

    def logout(self) -> None:
        self.timer.stop()
        if self.logout_callback:
            self.logout_callback()

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")
