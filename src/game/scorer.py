from __future__ import annotations

from typing import Optional

from data.models import Student
from game.rounds import INFO_KEYS


def normalized(value: str) -> str:
    return "".join(str(value).strip().split()).lower()


def text_matches(expected: str, actual: str) -> bool:
    exp = normalized(expected)
    act = normalized(actual)
    if not exp:
        return not act
    return exp == act or exp in act or act in exp


def score_student_fields(
    student: Student,
    answers: dict[str, str],
    max_score: float,
    answer_fields: Optional[list[str]] = None,
) -> tuple[float, dict[str, bool]]:
    result: dict[str, bool] = {}
    if not text_matches(student.name, answers.get("姓名", "")):
        return 0.0, {"姓名": False}
    result["姓名"] = True
    fields = [field for field in (answer_fields or ["姓名", *INFO_KEYS]) if field != "姓名"]
    per_field = max_score / (len(fields) + 1)
    score = per_field
    expected = student.answer_fields()
    for key in fields:
        ok = text_matches(expected.get(key, ""), answers.get(key, ""))
        result[key] = ok
        if ok:
            score += per_field
    return round(score, 2), result


def score_locate(student: Student, answer: str) -> float:
    return 10.0 if text_matches(student.name, answer) else 0.0


def total_score(scores: dict[str, float]) -> float:
    return round(sum(value for key, value in scores.items() if key != "总分"), 2)
