from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from data.models import Counselor, Student
from game import data_manager
from game.rounds import (
    build_locate_questions,
    build_mixed_round,
    build_needle_round,
    format_student_answer,
)


class DisplayWindow(QMainWindow):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.setCentralWidget(self.browser)
        self.resize(960, 640)

    def set_content(self, title: str, body: str, zoom: int) -> None:
        font_size = max(14, int(18 * zoom / 100))
        image_width = max(120, int(180 * zoom / 100))
        html = f"""
        <html>
        <head>
        <style>
        body {{
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            font-size: {font_size}px;
            line-height: 1.55;
            margin: 22px;
        }}
        h1 {{
            font-size: {font_size + 8}px;
            margin-bottom: 14px;
        }}
        .grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .card {{
            border: 1px solid #90a4ae;
            border-radius: 6px;
            padding: 10px;
            margin: 8px;
            display: inline-block;
            vertical-align: top;
        }}
        img {{
            max-width: {image_width}px;
            max-height: {image_width}px;
        }}
        .muted {{
            color: #607d8b;
        }}
        </style>
        </head>
        <body><h1>{escape(title)}</h1>{body}</body>
        </html>
        """
        self.browser.setHtml(html)

    def move_to_screen(self, index: int) -> None:
        screens = QGuiApplication.screens()
        if not screens:
            return
        screen = screens[min(max(index, 0), len(screens) - 1)]
        self.setGeometry(screen.availableGeometry())
        self.showMaximized()


class CompetitionControlWindow(QMainWindow):
    def __init__(
        self,
        activity_path: Path,
        close_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"比赛控制台 - {activity_path.name}")
        self.activity_path = activity_path
        self.close_callback = close_callback
        self.settings = data_manager.get_contest_settings()
        self.answer_fields = list(self.settings["answer_fields"])
        self.counselors = self.load_competitors()
        self.current_index = 0
        self.current_round = "大海捞针"
        self.question_html = "<p>尚未开始。</p>"
        self.judge_html = "<p>尚未开始。</p>"
        self.remaining_seconds: Optional[int] = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.on_timer_tick)

        self.question_window = DisplayWindow("答题屏")
        self.judge_window = DisplayWindow("评委屏")
        self.build_ui()
        self.refresh_competitor_label()
        self.update_displays()

    def build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        self.title = QLabel("比赛控制台")
        self.title.setObjectName("titleLabel")
        layout.addWidget(self.title)

        nav = QHBoxLayout()
        self.prev_button = QPushButton("上一位")
        self.next_button = QPushButton("下一位")
        self.prev_button.clicked.connect(self.prev_competitor)
        self.next_button.clicked.connect(self.next_competitor)
        self.competitor_label = QLabel("")
        nav.addWidget(self.prev_button)
        nav.addWidget(self.next_button)
        nav.addWidget(self.competitor_label)
        nav.addStretch(1)
        layout.addLayout(nav)

        round_row = QHBoxLayout()
        self.round_combo = QComboBox()
        self.round_combo.addItems(["大海捞针", "鱼目混珠", "描述定位"])
        self.round_combo.currentTextChanged.connect(self.set_round)
        draw_button = QPushButton("生成/重抽题目")
        draw_button.clicked.connect(self.draw_round)
        self.timer_label = QLabel("计时：未开始")
        self.timer_button = QPushButton("开始计时")
        self.reset_timer_button = QPushButton("重置计时")
        self.timer_button.clicked.connect(self.toggle_timer)
        self.reset_timer_button.clicked.connect(self.reset_timer)
        round_row.addWidget(QLabel("比赛环节"))
        round_row.addWidget(self.round_combo)
        round_row.addWidget(draw_button)
        round_row.addWidget(self.timer_button)
        round_row.addWidget(self.reset_timer_button)
        round_row.addWidget(self.timer_label)
        round_row.addStretch(1)
        layout.addLayout(round_row)

        display_row = QHBoxLayout()
        self.question_screen = QComboBox()
        self.judge_screen = QComboBox()
        self.question_content = QComboBox()
        self.judge_content = QComboBox()
        self.question_content.addItems(["题目", "标准信息"])
        self.judge_content.addItems(["标准信息", "题目"])
        for combo in (self.question_screen, self.judge_screen):
            for index, screen in enumerate(QGuiApplication.screens()):
                combo.addItem(f"屏幕 {index + 1}: {screen.name()}", index)
        if self.judge_screen.count() > 1:
            self.judge_screen.setCurrentIndex(1)
        self.zoom = QSpinBox()
        self.zoom.setRange(70, 180)
        self.zoom.setValue(100)
        for widget in (self.question_screen, self.judge_screen, self.question_content, self.judge_content, self.zoom):
            if isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self.update_displays)
            else:
                widget.currentIndexChanged.connect(self.update_displays)
        display_row.addWidget(QLabel("答题屏"))
        display_row.addWidget(self.question_screen)
        display_row.addWidget(self.question_content)
        display_row.addWidget(QLabel("评委屏"))
        display_row.addWidget(self.judge_screen)
        display_row.addWidget(self.judge_content)
        display_row.addWidget(QLabel("缩放"))
        display_row.addWidget(self.zoom)
        layout.addLayout(display_row)

        action_row = QHBoxLayout()
        show_button = QPushButton("显示双屏")
        close_button = QPushButton("关闭双屏")
        finish_button = QPushButton("结束比赛")
        show_button.clicked.connect(self.show_displays)
        close_button.clicked.connect(self.close_displays)
        finish_button.clicked.connect(self.close)
        action_row.addWidget(show_button)
        action_row.addWidget(close_button)
        action_row.addWidget(finish_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.preview = QTextBrowser()
        layout.addWidget(self.preview)
        self.setCentralWidget(central)
        self.resize(980, 620)

    def load_competitors(self) -> list[Counselor]:
        counselors = data_manager.get_counselors(self.activity_path)
        selected = data_manager.get_contest_counselors(self.activity_path)
        if selected:
            order = {counselor_id: index for index, counselor_id in enumerate(selected)}
            counselors = [c for c in counselors if c.id in order]
            counselors.sort(key=lambda c: order[c.id])
        return counselors

    def current_counselor(self) -> Optional[Counselor]:
        if not self.counselors:
            return None
        return self.counselors[self.current_index]

    def refresh_competitor_label(self) -> None:
        counselor = self.current_counselor()
        if not counselor:
            self.competitor_label.setText("暂无参赛辅导员")
            return
        self.competitor_label.setText(f"当前：{self.current_index + 1}/{len(self.counselors)}  {counselor.id}")

    def set_round(self, text: str) -> None:
        self.current_round = text
        self.reset_round()

    def prev_competitor(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.refresh_competitor_label()
            self.reset_round()

    def next_competitor(self) -> None:
        if self.current_index < len(self.counselors) - 1:
            self.current_index += 1
            self.refresh_competitor_label()
            self.reset_round()

    def reset_round(self) -> None:
        self.timer.stop()
        self.remaining_seconds = None
        self.timer_button.setText("开始计时")
        self.timer_label.setText("计时：未开始")
        self.question_html = "<p>请生成题目。</p>"
        self.judge_html = "<p>请生成题目。</p>"
        self.update_displays()

    def round_duration(self) -> int:
        key_map = {
            "大海捞针": "needle_duration_seconds",
            "鱼目混珠": "mixed_duration_seconds",
            "描述定位": "locate_duration_seconds",
        }
        return int(self.settings.get(key_map[self.current_round], 120))

    def reset_timer(self) -> None:
        self.timer.stop()
        self.remaining_seconds = self.round_duration()
        self.timer_button.setText("开始计时")
        self.update_timer_label()
        self.update_displays()

    def toggle_timer(self) -> None:
        if self.remaining_seconds is None:
            self.reset_timer()
        if self.remaining_seconds is not None and self.remaining_seconds <= 0:
            return
        if self.timer.isActive():
            self.timer.stop()
            self.timer_button.setText("继续计时")
        else:
            self.timer.start()
            self.timer_button.setText("暂停计时")
        self.update_timer_label()

    def on_timer_tick(self) -> None:
        if self.remaining_seconds is None:
            return
        self.remaining_seconds = max(0, self.remaining_seconds - 1)
        if self.remaining_seconds == 0:
            self.timer.stop()
            self.timer_button.setText("开始计时")
        self.update_timer_label()
        self.update_displays()

    def update_timer_label(self) -> None:
        self.timer_label.setText(f"计时：{self.timer_text()}")

    def timer_text(self) -> str:
        if self.remaining_seconds is None:
            return "未开始"
        if self.remaining_seconds <= 0:
            return "时间到"
        minutes, seconds = divmod(self.remaining_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def draw_round(self) -> None:
        counselor = self.current_counselor()
        if not counselor:
            QMessageBox.warning(self, "无法开始", "当前活动没有参赛辅导员。")
            return
        students = data_manager.load_students(counselor.excel_path, counselor.photos_dir)
        try:
            if self.current_round == "大海捞针":
                round_data = build_needle_round(
                    students,
                    count=int(self.settings["needle_student_count"]),
                    duration_seconds=int(self.settings["needle_duration_seconds"]),
                )
                self.question_html = self.render_photo_cards(round_data.students, show_names=False)
                self.judge_html = self.render_answers(round_data.students)
            elif self.current_round == "鱼目混珠":
                other_ids = [c.id for c in self.counselors if c.id != counselor.id]
                others = data_manager.load_all_students_for_judge(self.activity_path, other_ids)
                round_data = build_mixed_round(
                    students,
                    others,
                    own_count=int(self.settings["mixed_own_count"]),
                    distractor_count=int(self.settings["mixed_distractor_count"]),
                    duration_seconds=int(self.settings["mixed_duration_seconds"]),
                )
                self.question_html = self.render_photo_cards(round_data.all_students, show_names=False)
                self.judge_html = "<h2>本人学生</h2>" + self.render_answers(round_data.own_students)
            else:
                questions = build_locate_questions(students, count=int(self.settings["locate_question_count"]))
                self.question_html = "".join(
                    f"<div class='card'><h2>题 {index}</h2>{self.render_clues(question.clues)}</div>"
                    for index, question in enumerate(questions, start=1)
                )
                self.judge_html = "".join(
                    f"<div class='card'><h2>题 {index}</h2>{self.render_clues(question.clues)}<p><b>答案：</b>{question.answer.name}</p></div>"
                    for index, question in enumerate(questions, start=1)
                )
        except Exception as exc:
            QMessageBox.warning(self, "抽题失败", str(exc))
            return
        self.reset_timer()
        self.update_displays()
        self.show_displays()

    def render_photo_cards(self, students: list[Student], show_names: bool) -> str:
        cards = ["<div class='grid'>"]
        for student in students:
            img = self.image_tag(student)
            name = f"<p><b>{escape(student.name)}</b></p>" if show_names else ""
            cards.append(f"<div class='card'>{img}<p class='muted'>{escape(student.student_id)}</p>{name}</div>")
        cards.append("</div>")
        return "".join(cards)

    def image_tag(self, student: Student) -> str:
        if student.photo_path and student.photo_path.exists():
            url = QUrl.fromLocalFile(str(student.photo_path)).toString()
            return f"<img src='{url}' />"
        return "<p>无照片</p>"

    def render_answers(self, students: list[Student]) -> str:
        return "".join(
            f"<div class='card'>{self.image_tag(student)}<pre>{escape(format_student_answer(student, self.answer_fields))}</pre></div>"
            for student in students
        )

    def render_clues(self, clues: dict[str, str]) -> str:
        return "<ul>" + "".join(f"<li><b>{escape(key)}：</b>{escape(value or '未填写')}</li>" for key, value in clues.items()) + "</ul>"

    def content_for(self, mode: str) -> tuple[str, str]:
        counselor = self.current_counselor()
        name = counselor.id if counselor else ""
        timer = self.timer_text()
        if mode == "题目":
            return f"{self.current_round} - {name} - {timer}", self.question_html
        return f"标准信息 - {self.current_round} - {name} - {timer}", self.judge_html

    def update_displays(self) -> None:
        q_title, q_body = self.content_for(self.question_content.currentText())
        j_title, j_body = self.content_for(self.judge_content.currentText())
        zoom = self.zoom.value()
        self.question_window.set_content(q_title, q_body, zoom)
        self.judge_window.set_content(j_title, j_body, zoom)
        self.preview.setHtml(f"<h2>答题屏预览</h2>{q_body}<hr><h2>评委屏预览</h2>{j_body}")

    def show_displays(self) -> None:
        self.question_window.move_to_screen(int(self.question_screen.currentData() or 0))
        self.judge_window.move_to_screen(int(self.judge_screen.currentData() or 0))
        self.update_displays()

    def close_displays(self) -> None:
        self.question_window.hide()
        self.judge_window.hide()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        self.close_displays()
        if self.close_callback:
            self.close_callback()
        super().closeEvent(event)
