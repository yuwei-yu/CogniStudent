from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from data.models import Student
from game import data_manager


INFO_KEYS = [
    "专业",
    "政治面貌",
    "担任职务",
    "家庭住址",
    "宿舍",
    "家庭经济状况",
    "心理健康状况",
    "英语四六级",
    "不及格科目",
    "奖惩情况",
]


@dataclass
class NeedleRound:
    students: list[Student]
    duration_seconds: int = 180
    max_score: float = 60.0


@dataclass
class MixedRound:
    own_students: list[Student]
    distractors: list[Student]
    duration_seconds: int = 120
    max_score: float = 40.0

    @property
    def all_students(self) -> list[Student]:
        students = [*self.own_students, *self.distractors]
        random.shuffle(students)
        return students


@dataclass
class LocateQuestion:
    answer: Student
    clues: dict[str, str]


def build_needle_round(students: list[Student], count: int = 3, duration_seconds: int = 180) -> NeedleRound:
    selected = random.sample(students, min(count, len(students)))
    return NeedleRound(students=selected, duration_seconds=duration_seconds)


def build_mixed_round(
    own_students: list[Student],
    other_students: list[Student],
    own_count: int = 2,
    distractor_count: int = 8,
    duration_seconds: int = 120,
) -> MixedRound:
    own = random.sample(own_students, min(own_count, len(own_students)))
    distractors = random.sample(other_students, min(distractor_count, len(other_students)))
    return MixedRound(own_students=own, distractors=distractors, duration_seconds=duration_seconds)


def build_locate_questions(students: list[Student], count: int = 2) -> list[LocateQuestion]:
    selected = random.sample(students, min(count, len(students)))
    questions: list[LocateQuestion] = []
    for student in selected:
        fields = {
            "专业": student.major,
            "经济状况": student.financial_status,
            "学习情况": student.failed_courses,
            "奖惩情况": student.awards,
            "家庭住址": student.hometown,
            "宿舍号": student.dormitory,
        }
        questions.append(LocateQuestion(answer=student, clues=fields))
    return questions


def format_student_answer(student: Student, answer_fields: Optional[list[str]] = None) -> str:
    values = student.answer_fields()
    fields = answer_fields or list(values.keys())
    return "\n".join(f"{key}：{student_field_value(student, key, values)}" for key in fields)


def student_field_value(student: Student, field: str, canonical_values: Optional[dict[str, str]] = None) -> str:
    values = canonical_values or student.answer_fields()
    if field in values:
        return values.get(field, "")
    if field in student.extra:
        return student.extra.get(field, "")
    for canonical, aliases in data_manager.COLUMN_ALIASES.items():
        if field == canonical or field in aliases:
            return values.get(canonical, student.extra.get(canonical, ""))
    stripped = field.strip()
    for key, value in student.extra.items():
        if str(key).strip() == stripped:
            return value
    return ""
