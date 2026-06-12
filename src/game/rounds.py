from __future__ import annotations

import random
from dataclasses import dataclass

from data.models import Student


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


def build_needle_round(students: list[Student]) -> NeedleRound:
    selected = random.sample(students, min(3, len(students)))
    return NeedleRound(students=selected)


def build_mixed_round(own_students: list[Student], other_students: list[Student]) -> MixedRound:
    own = random.sample(own_students, min(2, len(own_students)))
    distractors = random.sample(other_students, min(8, len(other_students)))
    return MixedRound(own_students=own, distractors=distractors)


def build_locate_questions(students: list[Student]) -> list[LocateQuestion]:
    selected = random.sample(students, min(2, len(students)))
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


def format_student_answer(student: Student) -> str:
    return "\n".join(f"{key}：{value or '未填写'}" for key, value in student.answer_fields().items())
