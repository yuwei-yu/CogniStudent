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
        layout.addWidget(self.title_label)
        layout.addWidget(self.browser)
        self.setCentralWidget(central)
        self.resize(1000, 700)

    def set_content(self, title: str, body: str) -> None:
        self.title_label.setText(title)
        self.browser.setHtml(
            build_html_document(body, image_width=88, font_size=20, judge=True)
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
        self.judge_body_builder: Optional[Callable[[int], str]] = None
        self.round_ready = False
        self.question_revealed = False
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
        finish = QPushButton("结束答题")
        self.start_button = start
        draw.clicked.connect(self.draw_round)
        start.clicked.connect(self.start_timer)
        pause.clicked.connect(self.toggle_pause)
        finish.clicked.connect(self.finish_answering)
        controls.addWidget(QLabel("环节"))
        controls.addWidget(self.round_combo)
        controls.addWidget(draw)
        controls.addWidget(start)
        controls.addWidget(pause)
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
        self.judge_body_builder = None
        self.start_button.setText("开始计时")
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
                self.question_html = (
                    self.render_question_intro()
                    + self.render_photo_cards(round_data.students)
                )
                self.answer_html = self.render_answers(
                    round_data.students, columns=self.answer_columns()
                )
                self.judge_body_builder = (
                    lambda columns, students=round_data.students: self.render_answers(
                        students, judge=True, columns=columns
                    )
                )
                self.judge_html = self.judge_body_builder(self.judge_columns())
            elif self.current_round == "鱼目混珠":
                other_ids = [
                    c.id
                    for c in data_manager.get_counselors(self.activity_path)
                    if c.id != self.counselor.id
                ]
                others = data_manager.load_all_students_for_judge(
                    self.activity_path, other_ids
                )
                round_data = build_mixed_round(
                    self.students,
                    others,
                    own_count=int(self.settings["mixed_own_count"]),
                    distractor_count=int(self.settings["mixed_distractor_count"]),
                    duration_seconds=int(self.settings["mixed_duration_seconds"]),
                )
                all_students = round_data.all_students
                self.question_html = (
                    self.render_question_intro() + self.render_photo_cards(all_students)
                )
                self.answer_html = "<h2>本人学生标准信息</h2>" + self.render_answers(
                    round_data.own_students, columns=self.answer_columns()
                )
                self.judge_body_builder = (
                    lambda columns, students=round_data.own_students: (
                        "<h2>本人学生标准信息</h2>"
                        + self.render_answers(students, judge=True, columns=columns)
                    )
                )
                self.judge_html = self.judge_body_builder(self.judge_columns())
            else:
                questions = build_locate_questions(
                    self.students, count=int(self.settings["locate_question_count"])
                )
                self.question_html = self.render_question_intro() + "".join(
                    f"<section class='info-card'><h2>题 {index}</h2>{self.render_clues(question.clues)}</section>"
                    for index, question in enumerate(questions, start=1)
                )
                self.answer_html = "".join(
                    f"<section class='info-card'><h2>题 {index}</h2>{self.render_clues(question.clues)}<p><b>答案：</b>{escape(question.answer.name)}</p></section>"
                    for index, question in enumerate(questions, start=1)
                )
                self.judge_body_builder = (
                    lambda columns, html=self.answer_html: html
                )
                self.judge_html = self.answer_html
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))
            return
        self.round_ready = True
        self.question_revealed = False
        self.remaining_seconds = self.round_duration()
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
        self.question_browser.setHtml(
            build_html_document(self.question_html, image_width=96, font_size=20)
        )
        self.judge_window.move_to_screen(int(self.judge_screen.currentData() or 0))
        self.update_judge_display()
        if self.remaining_seconds is None:
            self.remaining_seconds = self.round_duration()
        if self.remaining_seconds > 0:
            self.timer.start()
            self.start_button.setText("重新开始")

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

    def question_photo_columns(self) -> int:
        width = max(720, self.question_browser.viewport().width())
        return max(1, min(4, (width - 48) // 305))

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
        columns = self.question_photo_columns()
        cards = [
            "<table class='photo-table' width='100%' cellspacing='8' cellpadding='0'>"
        ]
        for index, student in enumerate(students):
            if index % columns == 0:
                cards.append("<tr>")
            cards.append(
                "<td class='photo-cell' valign='top' align='center'>"
                "<div class='question-photo-card'>"
                f"{self.image_tag(student, image_width=270, preserve_ratio=True)}"
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
        image_height = int(image_width * 1334 / 1002)
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
        columns = columns or (self.judge_columns() if judge else self.answer_columns())
        image_width = 78 if judge else 96
        card_class = "answer-card judge-answer-card" if judge else "answer-card"
        cards = [
            "<table class='answer-board' width='100%' cellspacing='14' cellpadding='0'>"
        ]
        for index, student in enumerate(students):
            if index % columns == 0:
                cards.append("<tr>")
            cards.append(
                "<td class='answer-cell' valign='top'>"
                f"<div class='{card_class}'>"
                "<table class='answer-card-table' width='100%' cellspacing='0' cellpadding='0'>"
                "<tr>"
                f"<td class='answer-photo' valign='top'>{self.image_tag(student, image_width=image_width)}</td>"
                f"<td class='answer-content' valign='top'><h2>{escape(student.name)}</h2><pre>{escape(format_student_answer(student, self.answer_fields))}</pre></td>"
                "</tr>"
                "</table>"
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
    # keep answer photos readable without letting large source images dominate the UI
    if not judge:
        image_width = min(image_width, 96)
    # judge images slightly smaller; non-judge images tightened further
    answer_image_width = 78 if judge else max(84, min(96, image_width))
    answer_image_height = int(answer_image_width * 1334 / 1002)
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
        margin: 12px 0 0 0;
    }}
    .photo-cell {{
        text-align: center;
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
    }}
    .photo-index {{
        display: inline;
        margin-top: 2px;
        padding: 2px 12px;
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
        object-fit: cover;
        object-position: center center;
        display: block;
    }}
    .missing-photo {{
        text-align: center;
        line-height: {answer_image_height}px;
        background: #e7eeee;
        color: #607d8b;
    }}

    body.judge {{
        line-height: 1.5;
    }}

    .judge .answer-board, body.judge .answer-board {{
        margin-top: 12px;
    }}
    .judge .answer-cell, body.judge .answer-cell {{
        vertical-align: top;
        padding: 4px;
    }}
    .judge .answer-card, body.judge .answer-card {{
        width: 100%;
        background: #ffffff;
        border: 1px solid #cbdcd8;
        border-left: 6px solid #8fb8ad;
        border-radius: 10px;
        box-shadow: 0 5px 16px rgba(35, 73, 78, 0.10);
    }}
    .judge .answer-photo, body.judge .answer-photo {{
        width: {answer_image_width + 24}px;
        padding: 12px;
        vertical-align: top;
        background: #f5faf8;
    }}
    .judge .answer-content, body.judge .answer-content {{
        padding: 12px 14px 12px 0;
        vertical-align: top;
    }}
    .judge .answer-content h2, body.judge .answer-content h2 {{
        display: inline-block;
        padding: 3px 10px;
        margin-bottom: 10px;
        border-radius: 6px;
        background: #dfeeea;
        color: #214b50;
        border: 1px solid #bdd8d1;
    }}
    .judge .answer-card img, body.judge .answer-card img {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
        max-width: {answer_image_width}px;
    }}
    .judge .answer-card .missing-photo, body.judge .answer-card .missing-photo {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
    }}
    .judge pre, body.judge pre {{
        white-space: pre-wrap;
        font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
        font-size: {answer_font_size}px;
        line-height: 1.72;
        margin: 0;
        color: #263b3f;
        background: #fbfdfc;
        border: 1px solid #dce9e6;
        border-radius: 6px;
        padding: 10px 12px;
    }}

    .competition .answer-board, body.competition .answer-board {{
        margin-top: 12px;
    }}
    .competition .answer-cell, body.competition .answer-cell {{
        vertical-align: top;
    }}
    .competition .answer-card, body.competition .answer-card {{
        width: 100%;
        background: #ffffff;
        border: 1px solid #d2e2df;
        border-left: 5px solid #2f8f83;
        border-radius: 8px;
        margin: 0;
        padding: 0;
        box-shadow: 0 4px 14px rgba(35, 73, 78, 0.09);
        border-collapse: separate;
    }}
    .competition .answer-photo, body.competition .answer-photo {{
        width: {answer_image_width + 24}px;
        padding: 12px;
        vertical-align: top;
        background: #f2f9f6;
    }}
    .competition .answer-content, body.competition .answer-content {{
        padding: 13px 16px 13px 6px;
        vertical-align: top;
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
    }}
    .competition .answer-card .missing-photo, body.competition .answer-card .missing-photo {{
        width: {answer_image_width}px;
        height: {answer_image_height}px;
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
        border: 1px solid #bfd7d2;
        border-left: 6px solid #2f8f83;
        border-radius: 8px;
        padding: 18px 22px 20px 22px;
        margin: 0 0 26px 0;
        box-shadow: 0 4px 14px rgba(35, 73, 78, 0.08);
    }}
    .field-title {{
        display: block;
        margin: 0 0 14px 0;
        color: #17484d;
        font-size: {max(16, font_size - 1)}px;
        font-weight: 700;
    }}
    .field-list {{
        line-height: 2.75;
    }}
    .field-pill {{
        display: inline-block;
        border: 1px solid #7dbab0;
        border-radius: 8px;
        padding: 9px 16px;
        background: #dff2ee;
        color: #0d3b40;
        white-space: nowrap;
        font-size: {max(18, font_size - 1)}px;
        line-height: 1.42;
        box-shadow: 0 2px 5px rgba(35, 73, 78, 0.06);
        margin: 0 10px 12px 0;
        font-weight: 600;
    }}
    .field-pill:hover {{
        background: #d2f0e8;
    }}

    .info-card {{
        background: #ffffff;
        border: 1px solid #d7e1df;
        border-radius: 8px;
        padding: 22px;
        margin-bottom: 18px;
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
