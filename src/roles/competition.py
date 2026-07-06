from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from data.models import Counselor, Student
from game import data_manager
from game.rounds import (
    LocateQuestion,
    build_locate_questions,
    build_mixed_round,
    build_needle_round,
    is_name_field,
    student_field_value,
)
from utils.logo import logo_label

PHOTO_HEIGHT_RATIO = 4 / 3


class JudgeDisplayWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("评委屏")
        self.title_label = QLabel("评委屏")
        self.title_label.setObjectName("titleLabel")
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        central = QWidget()
        layout = QVBoxLayout(central)
        header = QHBoxLayout()
        header.addWidget(logo_label(48))
        header.addWidget(self.title_label)
        header.addStretch(1)
        layout.addLayout(header)
        layout.addWidget(self.browser)
        self.setCentralWidget(central)
        self.resize(1000, 700)

    def set_content(self, title: str, body: str) -> None:
        self.title_label.setText(title)
        self.browser.setHtml(
            build_html_document(body, image_width=88, font_size=23, judge=True)
        )

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

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
        counselor: Counselor,
        finish_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.activity_path = activity_path
        self.counselor = counselor
        self.finish_callback = finish_callback
        self.settings = data_manager.get_contest_settings(activity_path)
        self.answer_fields = list(self.settings["answer_fields"])
        self.enabled_rounds = list(self.settings["enabled_rounds"])
        self.students = data_manager.load_students(
            counselor.excel_path, counselor.photos_dir
        )
        self.current_round = (
            self.enabled_rounds[0] if self.enabled_rounds else "大海捞针"
        )
        self.question_html = "<p>请先生成题目。</p>"
        self.judge_html = "<p>请先生成题目。</p>"
        self.answer_html = "<p>暂无答案。</p>"
        self.question_body_builder: Optional[Callable[[], str]] = None
        self.judge_body_builder: Optional[Callable[[int], str]] = None
        self.locate_questions: list[LocateQuestion] = []
        self.locate_index = 0
        self.round_ready = False
        self.question_revealed = False
        self.info_visible = False
        self.remaining_seconds: Optional[int] = None

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.on_timer_tick)
        self.judge_window = JudgeDisplayWindow()

        self.setWindowTitle(f"答题 - {counselor.id}")
        self.build_ui()
        self.reset_round()

    def build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        top = QHBoxLayout()
        self.title = QLabel(f"{self.counselor.id}")
        self.title.setObjectName("titleLabel")
        self.timer_label = QLabel("计时：未开始")
        self.timer_label.setObjectName("competitionTimer")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setMinimumWidth(190)
        self.timer_label.setStyleSheet(
            "QLabel#competitionTimer {"
            "font-size: 26px; font-weight: 800; color: #ffffff;"
            "background: #b42318; border: 2px solid #7a271a;"
            "border-radius: 8px; padding: 10px 18px;"
            "}"
        )
        top.addWidget(logo_label(46))
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.timer_label)
        layout.addLayout(top)

        controls = QHBoxLayout()
        self.round_combo = QComboBox()
        self.round_combo.addItems(self.enabled_rounds)
        self.round_combo.setMinimumWidth(130)
        self.round_combo.currentTextChanged.connect(self.change_round)
        self.judge_screen = QComboBox()
        self.judge_screen.setMinimumWidth(160)
        for index, screen in enumerate(QGuiApplication.screens()):
            self.judge_screen.addItem(f"屏幕 {index + 1}: {screen.name()}", index)
        if self.judge_screen.count() > 1:
            self.judge_screen.setCurrentIndex(1)
        draw = QPushButton("生成题目")
        start = QPushButton("开始计时")
        pause = QPushButton("暂停/继续")
        show_info = QPushButton("显示信息")
        prev_question = QPushButton("上一题")
        next_question = QPushButton("下一题")
        question_status = QLabel("")
        finish = QPushButton("结束答题")
        self.start_button = start
        self.show_info_button = show_info
        self.prev_question_button = prev_question
        self.next_question_button = next_question
        self.question_status_label = question_status
        self.question_status_label.setMinimumWidth(72)
        self.question_status_label.setAlignment(Qt.AlignCenter)
        self.show_info_button.setEnabled(False)
        self.prev_question_button.setEnabled(False)
        self.next_question_button.setEnabled(False)
        draw.clicked.connect(self.draw_round)
        start.clicked.connect(self.start_timer)
        pause.clicked.connect(self.toggle_pause)
        show_info.clicked.connect(self.toggle_student_info)
        prev_question.clicked.connect(self.previous_locate_question)
        next_question.clicked.connect(self.next_locate_question)
        finish.clicked.connect(self.finish_answering)
        controls.addWidget(QLabel("环节"))
        controls.addWidget(self.round_combo)
        controls.addWidget(draw)
        controls.addWidget(start)
        controls.addWidget(pause)
        controls.addWidget(show_info)
        controls.addWidget(prev_question)
        controls.addWidget(question_status)
        controls.addWidget(next_question)
        controls.addWidget(QLabel("评委屏"))
        controls.addWidget(self.judge_screen)
        controls.addWidget(finish)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.question_browser = QTextBrowser()
        self.question_browser.setOpenExternalLinks(False)
        layout.addWidget(self.question_browser)
        self.setCentralWidget(central)
        self.resize(1180, 760)

    def change_round(self, round_name: str) -> None:
        self.current_round = round_name
        self.reset_round()

    def reset_round(self) -> None:
        self.timer.stop()
        self.remaining_seconds = self.round_duration()
        self.round_ready = False
        self.question_revealed = False
        self.info_visible = False
        self.question_body_builder = None
        self.judge_body_builder = None
        self.locate_questions = []
        self.locate_index = 0
        self.start_button.setText("开始计时")
        self.show_info_button.setText("显示信息")
        self.show_info_button.setEnabled(False)
        self.update_locate_navigation()
        self.update_timer_label()
        self.question_browser.setHtml(
            build_html_document(
                "<p class='empty'>点击“生成题目”后开始。</p>",
                image_width=72,
                font_size=20,
            )
        )
        self.judge_window.set_content(
            f"{self.current_round} - {self.counselor.id}", "<p>等待生成题目。</p>"
        )

    def round_duration(self) -> int:
        key_map = {
            "大海捞针": "needle_duration_seconds",
            "鱼目混珠": "mixed_duration_seconds",
            "描述定位": "locate_duration_seconds",
        }
        return int(
            self.settings.get(
                key_map.get(self.current_round, "needle_duration_seconds"), 120
            )
        )

    def draw_round(self) -> None:
        try:
            if self.current_round == "大海捞针":
                round_data = build_needle_round(
                    self.students,
                    count=int(self.settings["needle_student_count"]),
                    duration_seconds=int(self.settings["needle_duration_seconds"]),
                )
                number_by_id = self.student_number_map(round_data.students)
                self.question_body_builder = (
                    lambda students=round_data.students, numbers=number_by_id: self.render_question_screen(
                        students, students, numbers
                    )
                )
                self.question_html = self.question_body_builder()
                self.answer_html = self.render_round_answer_table(round_data.students)
                self.judge_body_builder = (
                    lambda columns, students=round_data.students, numbers=number_by_id: self.render_judge_comparison_table(
                        students, numbers
                    )
                )
                self.judge_html = self.judge_body_builder(self.judge_columns())
            elif self.current_round == "鱼目混珠":
                other_ids = [
                    c.id
                    for c in data_manager.get_counselors(self.activity_path)
                    if c.id != self.counselor.id
                ]
                others = data_manager.load_student_sample_for_judge(
                    self.activity_path,
                    other_ids,
                    int(self.settings["mixed_distractor_count"]),
                )
                round_data = build_mixed_round(
                    self.students,
                    others,
                    own_count=int(self.settings["mixed_own_count"]),
                    distractor_count=int(self.settings["mixed_distractor_count"]),
                    duration_seconds=int(self.settings["mixed_duration_seconds"]),
                )
                all_students = round_data.all_students
                number_by_id = self.student_number_map(all_students)
                self.question_body_builder = (
                    lambda photo_students=all_students, info_students=round_data.own_students, numbers=number_by_id: self.render_question_screen(
                        photo_students, info_students, numbers
                    )
                )
                self.question_html = self.question_body_builder()
                self.answer_html = (
                    "<h2>本人学生标准信息</h2>"
                    + self.render_round_answer_table(round_data.own_students)
                )
                self.judge_body_builder = (
                    lambda columns, students=round_data.own_students, numbers=number_by_id: (
                        "<h2>本人学生标准信息</h2>"
                        + self.render_judge_comparison_table(students, numbers)
                    )
                )
                self.judge_html = self.judge_body_builder(self.judge_columns())
            else:
                questions = build_locate_questions(
                    self.students,
                    count=int(self.settings["locate_question_count"]),
                    clue_fields=self.answer_fields,
                )
                self.locate_questions = questions
                self.locate_index = 0
                self.question_body_builder = (
                    lambda: self.render_current_locate_question()
                )
                self.question_html = self.question_body_builder()
                self.answer_html = self.render_locate_answer_table(self.locate_questions)
                self.judge_body_builder = (
                    lambda columns: self.render_current_locate_judge_card()
                )
                self.judge_html = self.judge_body_builder(self.judge_columns())
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))
            return
        self.round_ready = True
        self.question_revealed = False
        self.info_visible = False
        self.remaining_seconds = self.round_duration()
        self.show_info_button.setText("显示信息")
        self.show_info_button.setEnabled(self.current_round in {"大海捞针", "鱼目混珠"})
        self.update_locate_navigation()
        self.update_timer_label()
        self.question_browser.setHtml(
            build_html_document(
                "<p class='empty'>题目已生成，点击“开始计时”后显示。</p>",
                image_width=72,
                font_size=20,
            )
        )
        self.update_judge_display()

    def start_timer(self) -> None:
        if not self.round_ready:
            QMessageBox.warning(self, "未生成题目", "请先生成题目。")
            return
        self.question_revealed = True
        self.remaining_seconds = self.round_duration()
        self.timer.stop()
        if self.question_body_builder:
            self.question_html = self.question_body_builder()
        self.question_browser.setHtml(
            build_html_document(self.question_html, image_width=96, font_size=20)
        )
        self.judge_window.move_to_screen(int(self.judge_screen.currentData() or 0))
        self.update_judge_display()
        if self.remaining_seconds > 0:
            self.timer.start()
            self.start_button.setText("重新开始")
        self.update_timer_label()

    def toggle_student_info(self) -> None:
        if not self.round_ready or not self.question_body_builder:
            return
        self.info_visible = not self.info_visible
        self.show_info_button.setText("隐藏信息" if self.info_visible else "显示信息")
        if self.question_revealed:
            self.question_html = self.question_body_builder()
            self.question_browser.setHtml(
                build_html_document(self.question_html, image_width=96, font_size=20)
            )

    def previous_locate_question(self) -> None:
        if self.current_round != "描述定位" or not self.locate_questions:
            return
        self.locate_index = max(0, self.locate_index - 1)
        self.refresh_current_locate_question()

    def next_locate_question(self) -> None:
        if self.current_round != "描述定位" or not self.locate_questions:
            return
        self.locate_index = min(len(self.locate_questions) - 1, self.locate_index + 1)
        self.refresh_current_locate_question()

    def refresh_current_locate_question(self) -> None:
        self.update_locate_navigation()
        if self.question_body_builder:
            self.question_html = self.question_body_builder()
        if self.question_revealed:
            self.question_browser.setHtml(
                build_html_document(self.question_html, image_width=96, font_size=20)
            )
        self.update_judge_display()

    def update_locate_navigation(self) -> None:
        locate_round = self.current_round == "描述定位"
        self.prev_question_button.setVisible(locate_round)
        self.next_question_button.setVisible(locate_round)
        self.question_status_label.setVisible(locate_round)
        active = locate_round and bool(self.locate_questions)
        total = len(self.locate_questions)
        current = self.locate_index + 1 if active else 0
        self.prev_question_button.setEnabled(active and self.locate_index > 0)
        self.next_question_button.setEnabled(active and self.locate_index < total - 1)
        self.question_status_label.setText(f"题 {current} / {total}" if active else "")

    def toggle_pause(self) -> None:
        if not self.round_ready:
            return
        if self.timer.isActive():
            self.timer.stop()
        elif self.remaining_seconds and self.remaining_seconds > 0:
            self.timer.start()

    def on_timer_tick(self) -> None:
        if self.remaining_seconds is None:
            return
        self.remaining_seconds = max(0, self.remaining_seconds - 1)
        if self.remaining_seconds == 0:
            self.timer.stop()
        self.update_timer_label()
        self.judge_window.set_title(
            f"评委标准信息 - {self.current_round} - {self.timer_text()}"
        )

    def update_timer_label(self) -> None:
        self.timer_label.setText(f"计时：{self.timer_text()}")

    def timer_text(self) -> str:
        if self.remaining_seconds is None:
            return "未开始"
        if self.remaining_seconds <= 0:
            return "时间到"
        minutes, seconds = divmod(self.remaining_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def update_judge_display(self) -> None:
        if self.judge_body_builder:
            self.judge_html = self.judge_body_builder(self.judge_columns())
        self.judge_window.set_content(
            f"评委标准信息 - {self.current_round} - {self.timer_text()}",
            self.judge_html,
        )

    def finish_answering(self) -> None:
        self.timer.stop()
        self.question_browser.setHtml(
            build_html_document(
                "<h2>标准答案</h2>" + self.answer_html, image_width=96, font_size=20
            )
        )
        self.update_judge_display()
        data_manager.record_counselor_attempt(self.activity_path, self.counselor.id)
        QMessageBox.information(self, "答题结束", "已显示标准答案，并记录本次参赛。")
        self.judge_window.hide()
        if self.finish_callback:
            self.finish_callback()
        self.close()

    def question_photo_layout(self, count: int) -> tuple[int, int]:
        count = max(1, count)
        viewport_width = max(640, self.question_browser.viewport().width())
        viewport_height = max(420, self.question_browser.viewport().height())
        available_width = max(420, viewport_width - 64)
        available_height = max(260, viewport_height - (168 if self.info_visible else 126))
        best_width = 1
        best_columns = 1
        max_columns = min(count, 12)
        aspect = PHOTO_HEIGHT_RATIO
        for columns in range(1, max_columns + 1):
            rows = (count + columns - 1) // columns
            cell_width = (available_width - (columns - 1) * 8) / columns
            cell_height = (available_height - (rows - 1) * 8) / rows - 34
            candidate = int(min(cell_width, cell_height / aspect))
            if candidate > best_width:
                best_width = candidate
                best_columns = columns
        best_width = max(44, min(320, best_width))
        return best_width, best_columns

    def answer_columns(self) -> int:
        width = max(760, self.question_browser.viewport().width())
        return max(1, min(3, (width - 48) // 430))

    def judge_columns(self) -> int:
        screens = QGuiApplication.screens()
        screen_width = self.judge_window.width()
        screen_index = int(self.judge_screen.currentData() or 0)
        if screens:
            screen = screens[min(max(screen_index, 0), len(screens) - 1)]
            screen_width = screen.availableGeometry().width()
        if self.judge_window.isVisible():
            screen_width = max(screen_width, self.judge_window.browser.viewport().width())
        return max(1, min(5, (screen_width - 56) // 390))

    def render_photo_cards(self, students: list[Student]) -> str:
        image_width, columns = self.question_photo_layout(len(students))
        cards = [
            "<table class='photo-table' width='100%' cellspacing='8' cellpadding='0'>"
        ]
        for index, student in enumerate(students):
            if index % columns == 0:
                cards.append("<tr>")
            cards.append(
                "<td class='photo-cell' valign='top' align='center'>"
                "<div class='question-photo-card'>"
                f"{self.image_tag(student, image_width=image_width, preserve_ratio=True)}"
                "<br />"
                f"<span class='photo-index'>{index + 1}</span>"
                "</div>"
                "</td>"
            )
            if index % columns == columns - 1:
                cards.append("</tr>")
        remainder = len(students) % columns
        if remainder:
            for _ in range(columns - remainder):
                cards.append("<td class='photo-cell photo-cell-empty'></td>")
            cards.append("</tr>")
        cards.append("</table>")
        return "".join(cards)

    def render_question_screen(
        self,
        photo_students: list[Student],
        info_students: list[Student],
        number_by_id: Optional[dict[int, int]] = None,
    ) -> str:
        body = self.render_question_intro() + self.render_photo_cards(photo_students)
        if self.info_visible:
            body += "<h2 class='student-info-title'>学生信息</h2>"
            body += self.render_answer_table(
                info_students, include_answer_label=False, number_by_id=number_by_id
            )
        return body

    def render_question_intro(self) -> str:
        fields = "&nbsp;&nbsp;".join(
            f"<span class='field-pill'>{escape(str(field))}</span>"
            for field in self.answer_fields
        )
        return (
            f"<div class='field-strip'><div class='field-title'>答题字段</div>"
            f"<div class='field-list'>{fields}</div></div>"
        )

    def image_tag(
        self, student: Student, image_width: int = 72, preserve_ratio: bool = False
    ) -> str:
        image_height = int(image_width * PHOTO_HEIGHT_RATIO)
        if preserve_ratio:
            if student.photo_path and student.photo_path.exists():
                url = QUrl.fromLocalFile(str(student.photo_path)).toString()
                return (
                    f"<img class='question-photo' src='{url}' "
                    f"width='{image_width}' height='{image_height}' "
                    f"style='width:{image_width}px;max-width:{image_width}px;"
                    f"height:{image_height}px;border-radius:6px;vertical-align:top;' />"
                )
            return (
                f"<div class='photo-img missing-photo' "
                f"style='width:{image_width}px;height:{image_height}px;line-height:{image_height}px;'>"
                "无照片</div>"
            )
        frame_style = (
            f"width:{image_width}px;height:{image_height}px;"
            "overflow:hidden;border-radius:6px;background:#e7eeee;"
            f"text-align:center;line-height:{image_height}px;"
        )
        if student.photo_path and student.photo_path.exists():
            url = QUrl.fromLocalFile(str(student.photo_path)).toString()
            return (
                f"<div class='photo-img' style='{frame_style}'>"
                f"<img src='{url}' width='{image_width}' height='{image_height}' "
                f"style='width:{image_width}px;height:{image_height}px;' />"
                "</div>"
            )
        return (
            f"<div class='photo-img missing-photo' style='{frame_style}'>无照片</div>"
        )

    def render_answers(
        self, students: list[Student], judge: bool = False, columns: Optional[int] = None
    ) -> str:
        columns = 3 if judge else (columns or self.answer_columns())
        image_width = 96 if judge else 96
        card_class = "answer-card judge-answer-card" if judge else "answer-card"
        spacing = "0" if judge else "14"
        cards = [
            f"<table class='answer-board' width='100%' cellspacing='{spacing}' cellpadding='0'>"
        ]
        for index, student in enumerate(students):
            if index % columns == 0:
                cards.append("<tr>")
            cards.append(
                "<td class='answer-cell' valign='top'>"
                f"<div class='{card_class}'>"
                f"<div class='answer-index'>编号 {index + 1}</div>"
                f"<div class='answer-photo'>{self.image_tag(student, image_width=image_width)}</div>"
                f"<div class='answer-content'><h2>{escape(student.name)}</h2>{self.render_answer_fields(student)}</div>"
                "</div>"
                "</td>"
            )
            if index % columns == columns - 1:
                cards.append("</tr>")
        remainder = len(students) % columns
        if remainder:
            for _ in range(columns - remainder):
                cards.append("<td class='answer-cell answer-cell-empty'></td>")
            cards.append("</tr>")
        cards.append("</table>")
        return "".join(cards)

    def student_number_map(self, students: list[Student]) -> dict[int, int]:
        return {id(student): index for index, student in enumerate(students, start=1)}

    def render_judge_comparison_table(
        self, students: list[Student], number_by_id: dict[int, int]
    ) -> str:
        if not students:
            return "<p class='empty'>暂无标准信息。</p>"
        fields = ["姓名", *[field for field in self.answer_fields if not is_name_field(field)]]
        headers = ["字段"] + [
            f"编号 {number_by_id.get(id(student), index)}"
            for index, student in enumerate(students, start=1)
        ]
        rows = [
            "<table class='judge-comparison-table' width='100%' cellspacing='0' cellpadding='0'>",
            "<thead><tr>",
            "".join(f"<th>{escape(header)}</th>" for header in headers),
            "</tr></thead><tbody>",
            "<tr><td class='judge-field-cell'>照片</td>",
        ]
        for student in students:
            rows.append(
                "<td class='judge-student-photo-cell'>"
                f"{self.image_tag(student, image_width=102)}"
                "</td>"
            )
        rows.append("</tr>")
        for field in fields:
            rows.append(f"<tr><td class='judge-field-cell'>{escape(str(field))}</td>")
            for student in students:
                rows.append(
                    "<td class='judge-value-cell'>"
                    f"{escape(str(student_field_value(student, field, student.answer_fields())))}"
                    "</td>"
                )
            rows.append("</tr>")
        rows.append("</tbody></table>")
        return "".join(rows)

    def render_answer_fields(self, student: Student, include_name: bool = True) -> str:
        values = student.answer_fields()
        rows = []
        for field in self.answer_fields:
            if is_name_field(field):
                if not include_name:
                    continue
                field = "姓名"
            rows.append(
                "<tr class='answer-info-row'>"
                f"<td class='answer-info-key'>{escape(str(field))}：</td>"
                f"<td class='answer-info-value'>{escape(str(student_field_value(student, field, values)))}</td>"
                "</tr>"
            )
        return (
            "<table class='answer-info-table' width='100%' cellspacing='0' cellpadding='0'>"
            + "".join(rows)
            + "</table>"
        )

    def render_round_answer_table(self, students: list[Student]) -> str:
        return (
            "<h2 class='answer-main-title'>标准学生信息</h2>"
            + self.render_answer_table(students, include_answer_label=False)
        )

    def render_answer_table(
        self,
        students: list[Student],
        include_answer_label: bool = True,
        number_by_id: Optional[dict[int, int]] = None,
    ) -> str:
        fields = [
            field
            for field in self.answer_fields
            if not (include_answer_label and is_name_field(field))
        ]
        headers = ["编号", *fields]
        if include_answer_label:
            headers.insert(1, "答案")
        rows = [
            "<table class='student-answer-table' width='100%' cellspacing='0' cellpadding='0'>",
            "<thead><tr>",
            "".join(f"<th>{escape(header)}</th>" for header in headers),
            "</tr></thead><tbody>",
        ]
        for index, student in enumerate(students, start=1):
            cells = [str(number_by_id.get(id(student), index) if number_by_id else index)]
            if include_answer_label:
                cells.append(student.name)
            cells.extend(
                student_field_value(student, field, student.answer_fields())
                for field in fields
            )
            rows.append(
                "<tr>"
                + "".join(f"<td>{escape(str(value))}</td>" for value in cells)
                + "</tr>"
            )
        rows.append("</tbody></table>")
        return "".join(rows)

    def render_locate_question_table(self, questions: list[LocateQuestion]) -> str:
        clue_fields = list(questions[0].clues.keys()) if questions else []
        rows = [
            "<table class='student-answer-table locate-question-table' width='100%' cellspacing='0' cellpadding='0'>",
            "<thead><tr>",
            "<th>题号</th>",
            "".join(f"<th>{escape(field)}</th>" for field in clue_fields),
            "</tr></thead><tbody>",
        ]
        for index, question in enumerate(questions, start=1):
            rows.append(
                "<tr>"
                f"<td>{index}</td>"
                + "".join(
                    f"<td>{escape(str(question.clues.get(field, '')))}</td>"
                    for field in clue_fields
                )
                + "</tr>"
            )
        rows.append("</tbody></table>")
        return "".join(rows)

    def render_current_locate_question(self) -> str:
        if not self.locate_questions:
            return "<p class='empty'>暂无描述定位题目。</p>"
        question = self.locate_questions[self.locate_index]
        return (
            f"<div class='locate-question-card'>"
            + f"<div class='locate-question-title'>题 {self.locate_index + 1} / {len(self.locate_questions)}</div>"
            + self.render_locate_question_table([question])
            + "</div>"
        )

    def render_locate_answer_table(self, questions: list[LocateQuestion]) -> str:
        students = [question.answer for question in questions]
        return (
            "<h2 class='answer-main-title'>描述定位标准答案</h2>"
            + self.render_answer_table(students, include_answer_label=False)
        )

    def render_current_locate_judge_card(self) -> str:
        if not self.locate_questions:
            return "<p class='empty'>暂无描述定位答案。</p>"
        question = self.locate_questions[self.locate_index]
        student = question.answer
        return (
            f"<div class='judge-page-title'>描述定位答案 - 题 {self.locate_index + 1} / {len(self.locate_questions)}</div>"
            "<table class='locate-detail-card' width='100%' cellspacing='0' cellpadding='0'>"
            "<tr>"
            "<td class='locate-detail-photo' valign='middle'>"
            f"{self.image_tag(student, image_width=220)}"
            "</td>"
            "<td class='locate-detail-info' valign='top'>"
            "<div class='locate-detail-head'>"
            f"<span class='locate-card-index'>#{self.locate_index + 1}</span>"
            f"<span class='locate-detail-name'>{escape(student.name)}</span>"
            "</div>"
            f"{self.render_answer_fields(student, include_name=False)}"
            "</td>"
            "</tr>"
            "</table>"
        )

    def render_locate_judge_cards(
        self,
        questions: list[LocateQuestion],
        start_index: int = 1,
        title: str = "描述定位答案",
    ) -> str:
        cards = [
            f"<div class='judge-page-title'>{escape(title)}</div>",
            "<table class='locate-judge-board' width='100%' cellspacing='18' cellpadding='0'>",
        ]
        columns = 3
        for index, question in enumerate(questions):
            if index % columns == 0:
                cards.append("<tr>")
            student = question.answer
            cards.append(
                "<td class='locate-judge-cell' valign='top'>"
                "<table class='locate-judge-card' width='100%' cellspacing='0' cellpadding='0'>"
                "<tr><td class='locate-card-head'>"
                f"<span class='locate-card-index'>#{start_index + index}</span>"
                f"<span class='locate-card-name'>{escape(student.name)}</span>"
                "</td></tr>"
                "<tr><td class='locate-card-photo'>"
                f"{self.image_tag(student, image_width=130)}"
                "</td></tr>"
                "</table>"
                "</td>"
            )
            if index % columns == columns - 1:
                cards.append("</tr>")
        remainder = len(questions) % columns
        if remainder:
            for _ in range(columns - remainder):
                cards.append("<td class='locate-judge-cell locate-judge-cell-empty'></td>")
            cards.append("</tr>")
        cards.append("</table>")
        return "".join(cards)

    def render_clues(self, clues: dict[str, str]) -> str:
        return (
            "<dl>"
            + "".join(
                f"<dt>{escape(key)}</dt><dd>{escape(str(value))}</dd>"
                for key, value in clues.items()
            )
            + "</dl>"
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self.timer.stop()
        self.judge_window.hide()
        super().closeEvent(event)


def build_html_document(
    body: str, image_width: int, font_size: int, judge: bool = False
) -> str:
    if not judge:
        image_width = min(image_width, 96)
    answer_image_width = 96 if judge else max(84, min(96, image_width))
    answer_image_height = int(answer_image_width * PHOTO_HEIGHT_RATIO)
    body_margin = 16 if judge else 26
    answer_font_size = max(17, font_size - 1) if judge else max(18, font_size - 1)
    judge_class = "judge" if judge else "competition"
    return f"""
    <html class="{judge_class}">
    <head>
    <style>
    body {{
        font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
        font-size: {font_size}px;
        line-height: 1.62;
        margin: {body_margin}px;
        color: #24383b;
        background: #f1f6f4;
    }}
    h2 {{
        margin: 0 0 12px 0;
        font-size: {font_size + 3}px;
        color: #152d31;
    }}
    .photo-table {{
        margin: 6px 0 0 0;
    }}
    .photo-cell {{
        text-align: center;
        padding: 0;
    }}
    .question-photo-card {{
        display: inline-block;
        margin: 0;
        padding: 0;
        line-height: 1.1;
        text-align: center;
    }}
    .question-photo {{
        border-radius: 6px;
        vertical-align: top;
        object-fit: contain;
        background: #ffffff;
        border: 1px solid #d6e2df;
    }}
    .photo-index {{
        display: inline-block;
        margin-top: 2px;
        padding: 1px 12px;
        border-radius: 8px;
        background: #dfeeea;
        border: 1px solid #bdd8d1;
        color: #214b50;
        font-size: {max(18, font_size)}px;
        font-weight: 700;
        line-height: 1.35;
    }}
    .photo-card {{
        display: inline-block;
        background: #ffffff;
        border: 1px solid #cfddda;
        border-radius: 8px;
        padding: 0;
        text-align: center;
        box-shadow: 0 4px 12px rgba(35, 73, 78, 0.07);
    }}
    .photo-img {{
        overflow: hidden;
        border-radius: 6px;
        background: #e7eeee;
        display: block;
    }}
    .photo-img img {{
        object-fit: contain;
        object-position: center center;
        display: block;
        background: #ffffff;
    }}
    .missing-photo {{
        text-align: center;
        line-height: {answer_image_height}px;
        background: #e7eeee;
        color: #607d8b;
    }}

    body.judge {{
        line-height: 1.52;
        background: #f6f7f8;
    }}

    .judge .answer-board, body.judge .answer-board {{
        margin-top: 16px;
        table-layout: fixed;
        border-collapse: separate;
        border-spacing: 18px 16px;
    }}
    .judge .answer-cell, body.judge .answer-cell {{
        vertical-align: top;
        padding: 0;
    }}
    .judge .answer-card, body.judge .answer-card {{
        width: 100%;
        background: #ffffff;
        border: 1px solid #d9dee3;
        border-radius: 14px;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
        overflow: hidden;
    }}
    .judge .answer-photo, body.judge .answer-photo {{
        width: auto;
        padding: 16px 16px 10px 16px;
        text-align: center;
        background: #fafafa;
        border-bottom: 1px solid #e2e5e8;
    }}
    .judge .answer-content, body.judge .answer-content {{
        padding: 14px 16px 16px 16px;
    }}
    .judge .answer-content h2, body.judge .answer-content h2 {{
        display: block;
        padding: 0 0 10px 0;
        margin: 0 0 12px 0;
        border-radius: 6px;
        background: transparent;
        color: #1f2933;
        border: 0;
        border-bottom: 1px solid #e2e5e8;
        text-align: left;
        font-size: {font_size + 4}px;
        font-weight: 800;
    }}
    .judge .answer-card img, body.judge .answer-card img {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
        max-width: {answer_image_width}px;
        object-fit: contain;
        background: #ffffff;
    }}
    .judge .answer-card .missing-photo, body.judge .answer-card .missing-photo {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
        margin: 0 auto;
    }}
    .judge pre, body.judge pre {{
        white-space: pre-wrap;
        font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
        font-size: {answer_font_size + 1}px;
        line-height: 1.72;
        margin: 0;
        color: #27313a;
        background: #ffffff;
        border: 1px solid #d9dee3;
        border-radius: 6px;
        padding: 14px 16px;
        font-weight: 600;
    }}
    .judge-comparison-table {{
        margin-top: 14px;
        table-layout: fixed;
        border-collapse: collapse;
        background: #ffffff;
        border: 1px solid #d7dde2;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
    }}
    .judge-comparison-table th {{
        padding: 14px 16px;
        border: 1px solid #d7dde2;
        background: #f1f4f7;
        color: #1f2937;
        font-size: {font_size + 1}px;
        font-weight: 900;
        text-align: center;
        word-break: break-word;
    }}
    .judge-comparison-table th:first-child {{
        width: 128px;
        text-align: left;
    }}
    .judge-comparison-table td {{
        padding: 14px 16px;
        border: 1px solid #dce2e7;
        color: #25313b;
        background: #ffffff;
        font-size: {font_size}px;
        line-height: 1.48;
        vertical-align: top;
        word-break: break-word;
        white-space: normal;
    }}
    .judge-comparison-table tbody tr:nth-child(even) td {{
        background: #f8fafb;
    }}
    .judge-field-cell {{
        width: 128px;
        color: #5c6a78;
        font-weight: 800;
        white-space: nowrap;
    }}
    .judge-value-cell {{
        font-weight: 650;
    }}
    .judge-student-photo-cell {{
        text-align: center;
        vertical-align: middle;
        background: #fbfcfd;
    }}
    .judge-student-photo-cell .photo-img, .judge-student-photo-cell img {{
        border-radius: 10px;
    }}
    .answer-info-table {{
        border-collapse: separate;
        border-spacing: 0 8px;
    }}
    .answer-info-key {{
        width: 128px;
        padding: 10px 8px 10px 14px;
        border: 1px solid #dce1e5;
        border-right: 0;
        border-radius: 8px 0 0 8px;
        background: #f8fafb;
        color: #66717d;
        font-weight: 700;
        white-space: nowrap;
        vertical-align: top;
    }}
    .answer-info-value {{
        padding: 10px 14px 10px 12px;
        border: 1px solid #dce1e5;
        border-left: 0;
        border-radius: 0 8px 8px 0;
        background: #ffffff;
        color: #1f2933;
        font-weight: 600;
        word-break: break-word;
        vertical-align: top;
    }}
    .judge .answer-info-key, body.judge .answer-info-key {{
        width: 146px;
        padding: 12px 10px 12px 16px;
        border-color: #d8dde2;
        background: #f6f8fa;
    }}
    .judge .answer-info-value, body.judge .answer-info-value {{
        padding: 12px 16px 12px 14px;
        border-color: #d8dde2;
        background: #ffffff;
    }}
    .answer-index {{
        display: block;
        background: #eef0f2;
        color: #2f3a44;
        font-size: {font_size}px;
        font-weight: 800;
        padding: 10px 14px;
        text-align: left;
        border-bottom: 1px solid #d8dde2;
    }}
    .judge-page-title {{
        margin: 0 0 12px 0;
        padding: 0 0 12px 0;
        color: #1f2937;
        border-bottom: 1px solid #d9dee3;
        font-size: {font_size + 6}px;
        font-weight: 900;
    }}
    .locate-judge-board {{
        table-layout: fixed;
    }}
    .locate-judge-cell {{
        padding: 0;
        vertical-align: top;
    }}
    .locate-judge-card {{
        background: #ffffff;
        border: 1px solid #d9dee3;
        border-radius: 14px;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
    }}
    .locate-card-head {{
        padding: 16px 18px 14px 18px;
        background: #ffffff;
        border-bottom: 1px solid #edf0f2;
        border-radius: 14px 14px 0 0;
        white-space: nowrap;
    }}
    .locate-card-index {{
        display: inline-block;
        padding: 5px 10px;
        margin-right: 12px;
        border-radius: 999px;
        background: #f1f5f9;
        border: 1px solid #dbe3ea;
        color: #475569;
        font-size: {max(16, font_size - 2)}px;
        font-weight: 800;
    }}
    .locate-card-name {{
        color: #1f2937;
        font-size: {font_size + 5}px;
        font-weight: 900;
        line-height: 1.2;
    }}
    .locate-detail-card {{
        margin-top: 24px;
        background: #ffffff;
        border: 1px solid #d9dee3;
        border-radius: 16px;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
    }}
    .locate-detail-photo {{
        width: 360px;
        padding: 34px 30px;
        background: #f8fafc;
        text-align: center;
        border-right: 1px solid #e3e7eb;
        border-radius: 16px 0 0 16px;
    }}
    .locate-detail-photo .photo-img, .locate-detail-photo img {{
        border-radius: 12px;
    }}
    .locate-detail-info {{
        padding: 34px 38px 36px 38px;
        background: #ffffff;
        border-radius: 0 16px 16px 0;
    }}
    .locate-detail-head {{
        margin: 0 0 22px 0;
        padding: 0 0 18px 0;
        border-bottom: 1px solid #e3e7eb;
    }}
    .locate-detail-name {{
        margin-left: 14px;
        color: #111827;
        font-size: {font_size + 12}px;
        font-weight: 900;
        vertical-align: middle;
    }}
    .locate-detail-card .answer-info-table {{
        margin-top: 4px;
    }}
    .locate-detail-card .answer-info-key {{
        width: 160px;
        padding: 13px 12px 13px 16px;
    }}
    .locate-detail-card .answer-info-value {{
        padding: 13px 18px 13px 16px;
    }}

    .competition .answer-board, body.competition .answer-board {{
        margin-top: 12px;
        table-layout: fixed;
    }}
    .competition .answer-cell, body.competition .answer-cell {{
        vertical-align: top;
    }}
    .competition .answer-card, body.competition .answer-card {{
        width: 100%;
        background: #ffffff;
        border: 1px solid #d4d8dc;
        border-radius: 8px;
        margin: 0;
        padding: 0;
        box-shadow: 0 1px 3px rgba(30, 41, 59, 0.06);
        border-collapse: separate;
        overflow: hidden;
    }}
    .competition .answer-photo, body.competition .answer-photo {{
        width: auto;
        padding: 12px 12px 4px 12px;
        background: #f2f9f6;
        text-align: center;
    }}
    .competition .answer-content, body.competition .answer-content {{
        padding: 8px 14px 14px 14px;
    }}
    .competition .answer-content h2, body.competition .answer-content h2 {{
        display: inline-block;
        padding: 3px 12px;
        margin-bottom: 10px;
        border-radius: 6px;
        color: #0d3b40;
        background: #dff2ee;
        border: 1px solid #bee0d9;
    }}
    .competition .answer-card img, body.competition .answer-card img {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
        max-width: {answer_image_width}px;
        object-fit: contain;
        background: #ffffff;
    }}
    .competition .answer-card .missing-photo, body.competition .answer-card .missing-photo {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
        margin: 0 auto;
    }}
    .competition pre, body.competition pre {{
        white-space: pre-wrap;
        font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
        font-size: {answer_font_size}px;
        line-height: 1.78;
        margin: 0;
        color: #203033;
        background: #fbfdfc;
        border: 1px solid #e0ece9;
        border-radius: 6px;
        padding: 12px 14px;
    }}

    .field-strip {{
        background: #ffffff;
        border: 1px solid #d4d8dc;
        border-radius: 8px;
        padding: 12px 18px 14px 18px;
        margin: 0 0 12px 0;
        box-shadow: 0 1px 3px rgba(30, 41, 59, 0.05);
    }}
    .field-title {{
        display: block;
        margin: 0 0 8px 0;
        color: #17484d;
        font-size: {max(16, font_size - 1)}px;
        font-weight: 700;
    }}
    .field-list {{
        line-height: 2.1;
    }}
    .field-pill {{
        display: inline-block;
        border: 1px solid #d5dbe0;
        border-radius: 8px;
        padding: 6px 12px;
        background: #f4f5f6;
        color: #2f3a44;
        white-space: nowrap;
        font-size: {max(18, font_size - 1)}px;
        line-height: 1.42;
        box-shadow: 0 2px 5px rgba(35, 73, 78, 0.06);
        margin: 0 8px 8px 0;
        font-weight: 600;
    }}
    .field-pill:hover {{
        background: #eceff1;
    }}

    .info-card {{
        background: #ffffff;
        border: 1px solid #d7e1df;
        border-radius: 8px;
        padding: 22px;
        margin-bottom: 18px;
    }}
    .student-info-title, .answer-main-title {{
        margin: 4px 0 22px 0;
        padding: 0 0 10px 0;
        border-radius: 0;
        color: #1f2937;
        background: transparent;
        border: 0;
        border-bottom: 1px solid #d9dee3;
        font-size: {font_size + 6}px;
        font-weight: 900;
    }}
    .locate-question-card {{
        margin-top: 18px;
        padding: 22px;
        background: #ffffff;
        border: 1px solid #d9dee3;
        border-radius: 14px;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
    }}
    .locate-question-title {{
        margin: 0 0 18px 0;
        padding: 0 0 12px 0;
        border-bottom: 1px solid #e2e6ea;
        color: #1f2937;
        font-size: {font_size + 6}px;
        font-weight: 900;
    }}
    .student-answer-table {{
        border-collapse: collapse;
        background: #ffffff;
        border: 1px solid #c8d0d2;
        box-shadow: 0 3px 10px rgba(35, 73, 78, 0.06);
        table-layout: fixed;
        margin-top: 10px;
    }}
    .student-answer-table th {{
        background: #f0f3f3;
        color: #21383c;
        font-size: {max(17, font_size - 1)}px;
        padding: 13px 14px;
        border: 1px solid #c8d0d2;
        font-weight: 800;
    }}
    .student-answer-table td {{
        padding: 13px 14px;
        border: 1px solid #d5dcde;
        vertical-align: top;
        background: #ffffff;
        word-break: break-word;
        font-size: {max(16, font_size - 2)}px;
        line-height: 1.42;
    }}
    .student-answer-table tbody tr:nth-child(even) td {{
        background: #f7f8f8;
    }}
    .judge .student-answer-table, body.judge .student-answer-table {{
        border: 1px solid #c6cdd0;
        box-shadow: none;
    }}
    .judge .student-answer-table th, body.judge .student-answer-table th {{
        background: #edf0f0;
        color: #263b3f;
        border: 1px solid #c6cdd0;
        font-size: {font_size}px;
        padding: 13px 14px;
    }}
    .judge .student-answer-table td, body.judge .student-answer-table td {{
        border: 1px solid #d2d8da;
        font-size: {font_size - 1}px;
        font-weight: 600;
        padding: 13px 14px;
        background: #ffffff;
    }}
    .judge .student-answer-table tbody tr:nth-child(even) td, body.judge .student-answer-table tbody tr:nth-child(even) td {{
        background: #f7f8f8;
    }}
    .locate-question-table th:first-child, .locate-question-table td:first-child {{
        width: 72px;
        text-align: center;
        font-weight: 800;
    }}
    .locate-card-photo {{
        padding: 20px 18px 22px 18px;
        background: #fbfcfd;
        text-align: center;
        border-radius: 0 0 14px 14px;
    }}
    .locate-card-photo .photo-img, .locate-card-photo img {{
        border-radius: 10px;
    }}
    dl {{
        display: grid;
        grid-template-columns: 130px 1fr;
        gap: 8px 14px;
        margin: 0;
    }}
    dt {{
        font-weight: 600;
        color: #496469;
    }}
    dd {{
        margin: 0;
    }}
    .empty {{
        font-size: {font_size + 4}px;
        color: #607d8b;
        padding: 32px;
        text-align: center;
    }}
    </style>
    </head>
    <body class="{judge_class}">{body}</body>
    </html>
    """
