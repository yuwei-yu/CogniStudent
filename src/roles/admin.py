from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
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


class DataImportWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, path: Path, activity_path: Path, is_zip: bool) -> None:
        super().__init__()
        self.path = path
        self.activity_path = activity_path
        self.is_zip = is_zip

    @Slot()
    def run(self) -> None:
        try:
            if self.is_zip:
                report = data_manager.upload_zip(
                    self.path,
                    self.activity_path,
                    overwrite=True,
                    replace_existing=True,
                )
            else:
                report = data_manager.upload_excel(
                    self.path,
                    self.activity_path,
                    overwrite=True,
                    replace_existing=True,
                )
        except Exception as exc:
            message = str(exc)
            try:
                log_path = data_manager.write_import_log(
                    self.activity_path,
                    "上传资料包" if self.is_zip else "上传Excel",
                    self.path,
                    {
                        "imported": [],
                        "skipped": [],
                        "warnings": [],
                        "errors": [str(exc)],
                    },
                )
                message = f"{message}\n\n日志：{log_path}"
            except Exception:
                pass
            self.failed.emit(message)
            return
        self.finished.emit(report)


class AdminWindow(QMainWindow):
    def __init__(
        self,
        logout_callback: Optional[Callable[[], None]] = None,
        theme_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(
            "西安理工大学辅导员素质能力提升“大练兵”——辨识学生项目 - 管理员"
        )
        self.logout_callback = logout_callback
        self.theme_callback = theme_callback
        self.import_thread: Optional[QThread] = None
        self.import_worker: Optional[DataImportWorker] = None
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

    def home_qss(self) -> str:
        if theme.current_theme() == "light":
            page = "#f7f8fc"
            panel = "#ffffff"
            panel_hover = "#ffffff"
            border = "#eef1f6"
            hover_border = "#dfe4ff"
            title = "#102033"
            muted = "#667085"
            footer = "#7a8494"
            icon_bg = "transparent"
            icon_border = "#dedbff"
            primary = "#635bff"
            secondary_bg = "#ffffff"
            secondary_border = "#b9b4ff"
        else:
            page = "#161b22"
            panel = "#20262e"
            panel_hover = "#222b36"
            border = "#323b46"
            hover_border = "#4f5dff"
            title = "#eef2f7"
            muted = "#c8d0da"
            footer = "#9aa4b2"
            icon_bg = "transparent"
            icon_border = "#4b5168"
            primary = "#7c72ff"
            secondary_bg = "#20262e"
            secondary_border = "#5b61a8"

        return f"""
            #homePage {{
                background: {page};
            }}
            #homeHeader {{
                background: {panel};
                border-bottom: 1px solid {border};
            }}
            #homeBrandTitle {{
                color: {title};
                background: transparent;
                font-size: 22px;
                font-weight: 800;
            }}
            #homeBrandSubtitle {{
                color: {muted};
                background: transparent;
                font-size: 13px;
                font-weight: 600;
            }}
            #homeTitle {{
                color: {title};
                background: transparent;
                font-size: 34px;
                font-weight: 900;
            }}
            #homeAccent {{
                background: {primary};
                border-radius: 2px;
                min-height: 4px;
                max-height: 4px;
            }}
            #homeSubtitle {{
                color: {muted};
                background: transparent;
                font-size: 16px;
                font-weight: 600;
            }}
            #homeCard {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            #homeCard:hover {{
                border: 1px solid {hover_border};
                background: {panel_hover};
            }}
            #homeCardTitle {{
                color: {title};
                background: transparent;
                font-size: 22px;
                font-weight: 850;
            }}
            #homeCardDesc {{
                color: {muted};
                background: transparent;
                font-size: 15px;
                font-weight: 600;
            }}
            #homeIconBox {{
                background: {icon_bg};
                color: {primary};
                border: 1px solid {icon_border};
                border-radius: 12px;
                font-size: 18px;
                font-weight: 900;
            }}
            #homePrimaryButton {{
                background: {primary};
                color: #ffffff;
                border: 1px solid {primary};
                border-radius: 7px;
                min-height: 38px;
                padding: 7px 22px;
                font-size: 15px;
                font-weight: 800;
            }}
            #homeSecondaryButton {{
                background: {secondary_bg};
                color: {primary};
                border: 1px solid {secondary_border};
                border-radius: 7px;
                min-height: 38px;
                padding: 7px 22px;
                font-size: 15px;
                font-weight: 800;
            }}
            #homeFooter {{
                color: {footer};
                background: transparent;
                font-size: 13px;
                font-weight: 600;
            }}
            """

    def activity_qss(self) -> str:
        if theme.current_theme() == "light":
            page = "#f7f8fc"
            panel = "#ffffff"
            border = "#e7ebf3"
            text = "#14243d"
            muted = "#6b768a"
            soft = "#f4f2ff"
            primary = "#5b55ff"
            table_alt = "#ffffff"
            table_grid = "#edf0f5"
            success = "#20b894"
        else:
            page = "#161b22"
            panel = "#20262e"
            border = "#323b46"
            text = "#eef2f7"
            muted = "#c8d0da"
            soft = "#252843"
            primary = "#7c72ff"
            table_alt = "#1b222a"
            table_grid = "#303944"
            success = "#34d399"

        return f"""
            #activityPage {{
                background: {page};
            }}
            #activityHeader, #activityFooter {{
                background: {panel};
                border-bottom: 1px solid {border};
            }}
            #activityFooter {{
                border-top: 1px solid {border};
                border-bottom: 0;
            }}
            #detailBackButton {{
                min-height: 42px;
                padding: 0 18px;
                border-radius: 8px;
                color: {text};
                background: {panel};
                border: 1px solid {border};
                font-size: 15px;
                font-weight: 800;
            }}
            #activityTitle {{
                color: {text};
                background: transparent;
                font-size: 24px;
                font-weight: 900;
            }}
            #activityCrumb, #activityFooterText {{
                color: {muted};
                background: transparent;
                font-size: 14px;
                font-weight: 700;
            }}
            #activityCountBadge {{
                color: {text};
                background: {panel};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 10px 18px;
                font-size: 16px;
                font-weight: 900;
            }}
            #activityCountMark {{
                color: {success};
                background: transparent;
                font-size: 18px;
                font-weight: 900;
            }}
            #sideCard, #tableShell {{
                background: {panel};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            #sideCardTitle {{
                color: {text};
                background: transparent;
                font-size: 16px;
                font-weight: 900;
            }}
            #sideActionButton, #sideActionPrimary {{
                min-height: 48px;
                text-align: left;
                padding: 0 20px;
                border-radius: 8px;
                border: 0;
                font-size: 16px;
                font-weight: 850;
            }}
            #sideActionPrimary {{
                color: {primary};
                background: {soft};
                border-left: 3px solid {primary};
            }}
            #sideActionButton {{
                color: {text};
                background: transparent;
            }}
            #sideFilterLabel {{
                color: {muted};
                background: transparent;
                font-size: 14px;
                font-weight: 800;
            }}
            #activityPagerButton {{
                min-height: 42px;
                padding: 0 18px;
                border-radius: 8px;
                color: {muted};
                background: {panel};
                border: 1px solid {border};
                font-size: 15px;
                font-weight: 800;
            }}
            #activityCurrentPage {{
                min-width: 42px;
                min-height: 42px;
                color: {primary};
                background: {panel};
                border: 1px solid {primary};
                border-radius: 8px;
                font-size: 15px;
                font-weight: 900;
            }}
            #activityPageLabel {{
                color: {text};
                background: transparent;
                font-size: 15px;
                font-weight: 800;
            }}
            QTableWidget#activityTable {{
                color: {text};
                background: {panel};
                alternate-background-color: {table_alt};
                border: 0;
                border-radius: 0;
                gridline-color: {table_grid};
                font-size: 15px;
                font-weight: 700;
            }}
            QTableWidget#activityTable::item {{
                background: transparent;
                padding: 0 10px;
            }}
            QHeaderView::section {{
                min-height: 54px;
            }}
            #contestStartButton {{
                min-height: 34px;
                border-radius: 7px;
                color: {primary};
                background: {soft};
                border: 1px solid {border};
                font-size: 14px;
                font-weight: 900;
                padding: 0 12px;
            }}
            """

    def build_home_page(self) -> QWidget:
        content = QWidget()
        self.home_content = content
        content.setObjectName("homePage")
        content.setStyleSheet(self.home_qss())
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("homeHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(42, 18, 42, 18)
        header_layout.setSpacing(14)
        header_layout.addWidget(logo_label(62))

        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand_title = QLabel("西安理工大学辅导员素质能力提升“大练兵”——辨识学生项目")
        brand_title.setObjectName("homeBrandTitle")
        brand_subtitle = QLabel("西安理工大学")
        brand_subtitle.setObjectName("homeBrandSubtitle")
        brand.addWidget(brand_title)
        brand.addWidget(brand_subtitle)
        header_layout.addLayout(brand)
        header_layout.addStretch(1)

        theme_button = QPushButton(f"切换主题（当前：{theme.current_theme_label()}）")
        theme_button.clicked.connect(lambda: self.switch_theme(theme_button))
        header_layout.addWidget(theme_button)
        logout = QPushButton("退出登录")
        logout.clicked.connect(self.logout)
        header_layout.addWidget(logout)
        layout.addWidget(header)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(76, 58, 76, 34)
        main_layout.setSpacing(0)

        title = QLabel("管理员工作台")
        title.setObjectName("homeTitle")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        accent = QFrame()
        accent.setObjectName("homeAccent")
        accent.setFixedWidth(34)
        main_layout.addWidget(accent, alignment=Qt.AlignHCenter)
        subtitle = QLabel("  ")
        subtitle.setObjectName("homeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addSpacing(18)
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(42)

        actions = (
            (
                "比赛详情",
                "导入资料并逐位辅导员进入答题。",
                "资料",
                "进入",
                self.open_default_activity,
                True,
            ),
            (
                "比赛设置",
                "设置题目、计时、抽题数量和答题字段。",
                "设置",
                "设置",
                self.show_settings,
                False,
            ),
            (
                "导入历史数据",
                "导入此前导出的完整历史数据 zip。",
                "导入",
                "上传 ZIP",
                self.import_history_data,
                False,
            ),
            (
                "一键导出全部数据",
                "导出完整 resources 数据，便于换电脑恢复。",
                "导出",
                "导出数据",
                self.export_all_data,
                False,
            ),
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(24)
        for index, (
            text,
            description,
            icon_text,
            button_text,
            slot,
            primary,
        ) in enumerate(actions):
            card = QFrame()
            card.setObjectName("homeCard")
            card.setMinimumHeight(190)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(26, 26, 26, 26)
            card_layout.setSpacing(24)

            icon = QLabel(icon_text)
            icon.setObjectName("homeIconBox")
            icon.setAlignment(Qt.AlignCenter)
            icon.setFixedSize(82, 82)
            card_layout.addWidget(icon, alignment=Qt.AlignTop)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(10)
            card_title = QLabel(text)
            card_title.setObjectName("homeCardTitle")
            card_desc = QLabel(description)
            card_desc.setObjectName("homeCardDesc")
            card_desc.setWordWrap(True)
            button = QPushButton(f"{button_text}  ->")
            button.setObjectName(
                "homePrimaryButton" if primary else "homeSecondaryButton"
            )
            button.clicked.connect(slot)
            text_layout.addWidget(card_title)
            text_layout.addWidget(card_desc)
            text_layout.addStretch(1)
            text_layout.addWidget(button, alignment=Qt.AlignLeft)
            card_layout.addLayout(text_layout, stretch=1)
            grid.addWidget(card, index // 2, index % 2)
        main_layout.addLayout(grid)
        main_layout.addStretch(1)

        footer = QLabel("西安理工大学")
        footer.setObjectName("homeFooter")
        footer.setAlignment(Qt.AlignCenter)
        main_layout.addSpacing(46)
        main_layout.addWidget(footer)
        layout.addWidget(main, stretch=1)
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
        self.activity_content = content
        content.setObjectName("activityPage")
        content.setStyleSheet(self.activity_qss())
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("activityHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 18, 28, 18)
        header_layout.setSpacing(16)
        back = QPushButton("< 返回")
        back.setObjectName("detailBackButton")
        back.clicked.connect(self.show_home)
        header_layout.addWidget(back)
        header_layout.addWidget(logo_label(56))
        self.activity_title = QLabel("比赛详情")
        self.activity_title.setObjectName("activityTitle")
        header_layout.addWidget(self.activity_title)
        self.activity_crumb_label = QLabel("> 比赛")
        self.activity_crumb_label.setObjectName("activityCrumb")
        header_layout.addWidget(self.activity_crumb_label)
        header_layout.addStretch(1)
        count_wrap = QFrame()
        count_wrap.setObjectName("activityCountBadge")
        count_layout = QHBoxLayout(count_wrap)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.setSpacing(8)
        count_mark = QLabel("✓")
        count_mark.setObjectName("activityCountMark")
        self.contest_count_label = QLabel("已答题：0 / 0")
        self.contest_count_label.setObjectName("activityPageLabel")
        count_layout.addWidget(count_mark)
        count_layout.addWidget(self.contest_count_label)
        header_layout.addWidget(count_wrap)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(28, 18, 28, 18)
        body_layout.setSpacing(18)

        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(16)

        data_card = QFrame()
        data_card.setObjectName("sideCard")
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(18, 18, 18, 18)
        data_layout.setSpacing(12)
        data_title = QLabel("资料管理")
        data_title.setObjectName("sideCardTitle")
        data_layout.addWidget(data_title)
        data_actions = (
            ("上传资料", self.upload_zip, "sideActionPrimary"),
            ("下载模板", self.download_template, "sideActionButton"),
            ("刷新", self.refresh_counselors, "sideActionButton"),
        )
        for text, slot, object_name in data_actions:
            button = QPushButton(text)
            button.setObjectName(object_name)
            button.clicked.connect(slot)
            data_layout.addWidget(button)
        sidebar_layout.addWidget(data_card)

        filter_card = QFrame()
        filter_card.setObjectName("sideCard")
        filter_layout = QVBoxLayout(filter_card)
        filter_layout.setContentsMargins(18, 18, 18, 18)
        filter_layout.setSpacing(12)
        filter_title = QLabel("筛选与排序")
        filter_title.setObjectName("sideCardTitle")
        filter_layout.addWidget(filter_title)
        sort_label = QLabel("排序方式")
        sort_label.setObjectName("sideFilterLabel")
        filter_layout.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["工号升序", "工号降序"])
        self.sort_combo.currentIndexChanged.connect(
            lambda _=0: self.reset_page_and_refresh()
        )
        filter_layout.addWidget(self.sort_combo)
        self.unplayed_only = QCheckBox("只看未参赛")
        self.unplayed_only.stateChanged.connect(
            lambda _=0: self.reset_page_and_refresh()
        )
        filter_layout.addWidget(self.unplayed_only)
        filter_layout.addStretch(1)
        sidebar_layout.addWidget(filter_card, stretch=1)
        body_layout.addWidget(sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(18)

        pager_row = QHBoxLayout()
        pager_row.addStretch(1)
        prev_page = QPushButton("上一页")
        prev_page.setObjectName("activityPagerButton")
        next_page = QPushButton("下一页")
        next_page.setObjectName("activityPagerButton")
        prev_page.clicked.connect(self.prev_page)
        next_page.clicked.connect(self.next_page)
        self.current_page_badge = QLabel("1")
        self.current_page_badge.setObjectName("activityCurrentPage")
        self.current_page_badge.setAlignment(Qt.AlignCenter)
        self.page_label = QLabel("共 1 页")
        self.page_label.setObjectName("activityPageLabel")
        pager_row.addWidget(prev_page)
        pager_row.addWidget(self.current_page_badge)
        pager_row.addWidget(next_page)
        pager_row.addSpacing(18)
        pager_row.addWidget(self.page_label)
        main_layout.addLayout(pager_row)

        table_shell = QFrame()
        table_shell.setObjectName("tableShell")
        table_layout = QVBoxLayout(table_shell)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("activityTable")
        self.table.setHorizontalHeaderLabels(
            ["#", "参赛", "姓名", "工号", "学生数", "次数", "EXCEL"]
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 64)
        self.table.setColumnWidth(1, 150)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(76)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.cellClicked.connect(self.handle_activity_table_click)
        table_layout.addWidget(self.table)
        main_layout.addWidget(table_shell, stretch=1)
        body_layout.addWidget(main, stretch=1)
        layout.addWidget(body, stretch=1)

        footer = QFrame()
        footer.setObjectName("activityFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 12, 0, 12)
        footer_text = QLabel("西安理工大学 · 辅导员辨认学生系统")
        footer_text.setObjectName("activityFooterText")
        footer_layout.addStretch(1)
        footer_layout.addWidget(footer_text)
        footer_layout.addStretch(1)
        layout.addWidget(footer)
        return self.scroll_page(content)

    def show_home(self) -> None:
        self.stack.setCurrentWidget(self.home_page)

    def show_settings(self) -> None:
        self.rebuild_settings_page()
        self.stack.setCurrentWidget(self.settings_page)

    def open_default_activity(self) -> None:
        self.select_activity(
            data_manager.get_current_activity() or data_manager.DEFAULT_ACTIVITY_NAME
        )

    def select_activity(self, name: str) -> None:
        self.current_activity = name
        data_manager.set_current_activity(name)
        self.activity_path = data_manager.activity_path(name)
        self.activity_title.setText("比赛详情")
        self.activity_crumb_label.setText(f"> {name}")
        self.current_page = 0
        self.refresh_counselors()
        self.stack.setCurrentWidget(self.activity_page)

    def refresh_counselors(self) -> None:
        if not self.activity_path:
            return
        counselors = data_manager.get_counselors(self.activity_path)
        attempts = data_manager.load_attempts(self.activity_path)
        if self.unplayed_only.isChecked():
            counselors = [
                counselor
                for counselor in counselors
                if attempts.get(counselor.id, 0) <= 0
            ]
        reverse = self.sort_combo.currentIndex() == 1
        counselors.sort(
            key=lambda counselor: counselor.employee_id or counselor.id, reverse=reverse
        )
        self.current_counselors = counselors
        page_count = max(1, (len(counselors) + self.page_size - 1) // self.page_size)
        self.current_page = min(self.current_page, page_count - 1)
        start = self.current_page * self.page_size
        page_counselors = counselors[start : start + self.page_size]
        self.table.setRowCount(len(page_counselors))
        for row, counselor in enumerate(page_counselors):
            attempts_count = attempts.get(counselor.id, 0)
            number_item = QTableWidgetItem(str(start + row + 1))
            number_item.setTextAlignment(Qt.AlignCenter)
            number_item.setData(Qt.UserRole, counselor.id)
            self.table.setItem(row, 0, number_item)

            button = QPushButton("开始比赛" if attempts_count <= 0 else "再次参赛")
            button.setObjectName("contestStartButton")
            button.setMinimumHeight(34)
            button.setFixedWidth(112)
            button.clicked.connect(
                lambda _checked=False, counselor=counselor: self.start_counselor_competition(
                    counselor
                )
            )
            button_box = QWidget()
            button_box.setStyleSheet("background: transparent;")
            button_layout = QHBoxLayout(button_box)
            button_layout.setContentsMargins(8, 6, 8, 6)
            button_layout.addStretch(1)
            button_layout.addWidget(button)
            button_layout.addStretch(1)
            self.table.setCellWidget(row, 1, button_box)
            self.table.setRowHeight(row, 76)

            values = [
                (2, counselor.name, Qt.AlignCenter),
                (3, counselor.employee_id, Qt.AlignCenter),
                (4, self.student_count_text(counselor), Qt.AlignCenter),
                (5, str(attempts_count), Qt.AlignCenter),
                (
                    6,
                    f"▣{counselor.excel_path.name}",
                    Qt.AlignVCenter | Qt.AlignLeft,
                ),
            ]
            for col, value, alignment in values:
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, counselor.id)
                item.setTextAlignment(alignment)
                self.table.setItem(row, col, item)
        completed = sum(
            1
            for count in data_manager.load_attempts(self.activity_path).values()
            if count > 0
        )
        total = len(data_manager.get_counselors(self.activity_path))
        self.update_contest_count_label(completed, total)
        self.current_page_badge.setText(str(self.current_page + 1))
        self.page_label.setText(f"共 {page_count} 页")

    def reset_page_and_refresh(self) -> None:
        self.current_page = 0
        self.refresh_counselors()

    def handle_activity_table_click(self, row: int, column: int) -> None:
        if column != 1:
            return
        index = self.current_page * self.page_size + row
        if 0 <= index < len(self.current_counselors):
            self.start_counselor_competition(self.current_counselors[index])

    def update_contest_count_label(
        self, contest_count: Optional[int] = None, total_count: Optional[int] = None
    ) -> None:
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
        page_count = max(
            1, (len(self.current_counselors) + self.page_size - 1) // self.page_size
        )
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
            spin.setValue(
                int(settings.get(key, data_manager.DEFAULT_CONTEST_SETTINGS[key]))
            )
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
        add_field.clicked.connect(
            lambda _=False, layout=fields_layout, edits=field_edits: self.add_field_row(
                layout, edits, ""
            )
        )
        group_layout.addWidget(QLabel("答题字段"))
        group_layout.addLayout(fields_layout)
        group_layout.addWidget(add_field)
        save = QPushButton("保存全局设置")
        save.clicked.connect(
            partial(self.save_global_settings, round_checks, spin_widgets, field_edits)
        )
        group_layout.addWidget(save)
        self.settings_layout.addWidget(group)

    def add_field_row(
        self, layout: QVBoxLayout, edits: list[QLineEdit], value: str
    ) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        edit = QLineEdit(value)
        edit.setMinimumWidth(180)
        rename = QPushButton("编辑")
        remove = QPushButton("删除")
        rename.clicked.connect(lambda: edit.setFocus())
        remove.clicked.connect(
            lambda: (edits.remove(edit) if edit in edits else None, row.deleteLater())
        )
        row_layout.addWidget(edit)
        row_layout.addWidget(rename)
        row_layout.addWidget(remove)
        row_layout.addStretch(1)
        edits.append(edit)
        layout.addWidget(row)

    def save_global_settings(
        self, round_checks: dict, spin_widgets: dict, field_edits: list[QLineEdit]
    ) -> None:
        enabled_rounds = [
            name for name, check in round_checks.items() if check.isChecked()
        ]
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
        if self.import_thread is not None and self.import_thread.isRunning():
            QMessageBox.information(self, "正在导入", "资料正在导入中，请稍候。")
            return
        data_file, _ = QFileDialog.getOpenFileName(
            self, "选择资料文件", "", "Excel/Zip files (*.xlsx *.zip)"
        )
        if not data_file:
            return
        if (
            QMessageBox.question(
                self,
                "确认覆盖",
                "上传新资料会删除当前比赛已导入的所有辅导员资料、答题次数和成绩，然后使用本次资料重新导入。是否继续？",
            )
            != QMessageBox.Yes
        ):
            return
        self.start_data_import(Path(data_file))

    def start_data_import(self, path: Path) -> None:
        if not self.activity_path:
            return
        self.setEnabled(False)
        self.statusBar().showMessage("正在导入资料，请稍候...")
        thread = QThread(self)
        worker = DataImportWorker(
            path,
            self.activity_path,
            path.suffix.lower() == ".zip",
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.on_data_import_finished)
        worker.failed.connect(self.on_data_import_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self.on_data_import_thread_finished)
        self.import_thread = thread
        self.import_worker = worker
        thread.start()

    @Slot(dict)
    def on_data_import_finished(self, report: dict) -> None:
        self.setEnabled(True)
        self.statusBar().clearMessage()
        self.refresh_counselors()
        text = f"导入：{len(report['imported'])}；跳过：{len(report['skipped'])}；警告：{len(report['warnings'])}；错误：{len(report['errors'])}"
        details = "\n".join(report["warnings"] + report["errors"])
        log_path = report.get("log_path")
        log_text = f"\n\n日志：{log_path}" if log_path else ""
        QMessageBox.information(
            self,
            "导入完成",
            f"{text}\n\n{details}{log_text}" if details else f"{text}{log_text}",
        )

    @Slot(str)
    def on_data_import_failed(self, message: str) -> None:
        self.setEnabled(True)
        self.statusBar().clearMessage()
        QMessageBox.critical(self, "导入失败", message)

    @Slot()
    def on_data_import_thread_finished(self) -> None:
        self.import_thread = None
        self.import_worker = None
        self.setEnabled(True)
        self.statusBar().clearMessage()

    def download_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存上传模板", "template.zip", "Zip files (*.zip)"
        )
        if not path:
            return
        try:
            data_manager.download_template(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))
            return
        QMessageBox.information(self, "已保存", f"模板已保存到：{path}")

    def import_history_data(self) -> None:
        zip_file, _ = QFileDialog.getOpenFileName(
            self, "导入历史数据", "", "Zip files (*.zip)"
        )
        if not zip_file:
            return
        overwrite = (
            QMessageBox.question(self, "导入方式", "是否覆盖本机已有同名数据？")
            == QMessageBox.Yes
        )
        try:
            report = data_manager.import_data_package(
                Path(zip_file), overwrite=overwrite
            )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        log_path = report.get("log_path")
        log_text = f"\n\n日志：{log_path}" if log_path else ""
        QMessageBox.information(
            self,
            "导入完成",
            f"导入文件：{len(report['imported'])}；跳过：{len(report['skipped'])}{log_text}",
        )

    def export_all_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "一键导出全部数据", "CogniStudent_历史数据.zip", "Zip files (*.zip)"
        )
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
        try:
            self.competition_window = CompetitionControlWindow(
                self.activity_path,
                counselor,
                finish_callback=self.refresh_counselors,
            )
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", str(exc))
            return
        self.competition_window.show()
        self.competition_window.raise_()
        self.competition_window.activateWindow()

    def logout(self) -> None:
        if self.competition_window:
            self.competition_window.close()
            self.competition_window = None
        if self.logout_callback:
            self.logout_callback()

    def switch_theme(self, button: QPushButton) -> None:
        if self.theme_callback:
            self.theme_callback()
        if hasattr(self, "home_content"):
            self.home_content.setStyleSheet(self.home_qss())
        if hasattr(self, "activity_content"):
            self.activity_content.setStyleSheet(self.activity_qss())
        button.setText(f"切换主题（当前：{theme.current_theme_label()}）")
