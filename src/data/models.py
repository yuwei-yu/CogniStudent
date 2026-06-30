from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Student:
    student_id: str
    name: str
    major: str = ""
    political_status: str = ""
    position: str = ""
    hometown: str = ""
    dormitory: str = ""
    financial_status: str = ""
    mental_health: str = ""
    cet_status: str = ""
    failed_courses: str = ""
    awards: str = ""
    photo_path: Optional[Path] = None
    counselor_id: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def answer_fields(self) -> dict[str, str]:
        values = {
            "姓名": self.name,
            "专业": self.major,
            "政治面貌": self.political_status,
            "担任职务": self.position,
            "家庭住址": self.hometown,
            "宿舍": self.dormitory,
            "家庭经济状况": self.financial_status,
            "心理健康状况": self.mental_health,
            "英语四六级": self.cet_status,
            "不及格科目": self.failed_courses,
            "奖惩情况": self.awards,
        }
        for key, value in self.extra.items():
            if key not in values:
                values[key] = value
        return values


@dataclass
class Counselor:
    name: str
    employee_id: str
    base_name: str
    excel_path: Path
    photos_dir: Path

    @property
    def id(self) -> str:
        return self.base_name
