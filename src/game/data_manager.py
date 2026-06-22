from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

import pandas as pd

from data.models import Counselor, Student
from utils.helpers import app_root, bundled_root, copy_file, ensure_dir, read_json, resources_root, safe_activity_name, write_json


ADMIN_CONFIG = "admin_config.json"
CONTEST_CONFIG = "contest_config.json"
CONTEST_SETTINGS = "contest_settings.json"
SCORES_FILE = "scores.json"
ATTEMPTS_FILE = "contest_attempts.json"
CURRENT_ACTIVITY_FILE = ".current_activity.json"

DEFAULT_ADMIN = {"username": "admin", "password": "admin123"}

DEFAULT_CONTEST_SETTINGS = {
    "needle_duration_seconds": 180,
    "mixed_duration_seconds": 120,
    "locate_duration_seconds": 120,
    "needle_student_count": 3,
    "mixed_own_count": 2,
    "mixed_distractor_count": 8,
    "locate_question_count": 2,
    "enabled_rounds": ["大海捞针", "鱼目混珠", "描述定位"],
    "answer_fields": [
        "姓名",
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
    ],
}

REQUIRED_COLUMNS = [
    "学号",
    "姓名",
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

COLUMN_ALIASES = {
    "学号": ["学号", "学生学号", "学生编号", "编号"],
    "姓名": ["姓名", "学生姓名", "名字"],
    "专业": ["专业", "所在专业", "班级专业"],
    "政治面貌": ["政治面貌"],
    "担任职务": ["担任职务", "职务", "学生干部职务"],
    "家庭住址": ["家庭住址", "家庭住址省市级", "生源地", "家庭所在地"],
    "宿舍": ["宿舍", "宿舍楼号楼层", "宿舍号", "寝室"],
    "家庭经济状况": ["家庭经济状况", "经济状况"],
    "心理健康状况": ["心理健康状况", "心理状况"],
    "英语四六级": ["英语四六级", "英语四六级通过情况", "四六级"],
    "不及格科目": ["不及格科目", "上学年不及格科目门次", "挂科门次"],
    "奖惩情况": ["奖惩情况", "奖励惩处", "获奖情况"],
}

CURRENT_ACTIVITY: Optional[str] = None


def bootstrap() -> None:
    root = ensure_dir(resources_root())
    ensure_default_config(root / ADMIN_CONFIG, DEFAULT_ADMIN)
    if not global_contest_settings_path().exists():
        save_contest_settings(DEFAULT_CONTEST_SETTINGS)


def ensure_default_config(path: Path, default: dict[str, str]) -> None:
    if not path.exists():
        write_json(path, default)


def get_activities() -> list[str]:
    bootstrap()
    ignored = {"__pycache__"}
    return sorted(
        p.name
        for p in resources_root().iterdir()
        if p.is_dir() and p.name not in ignored and not p.name.startswith(".")
    )


def activity_path(activity_name: str) -> Path:
    return resources_root() / activity_name


def set_current_activity(activity_name: str) -> None:
    global CURRENT_ACTIVITY
    CURRENT_ACTIVITY = activity_name
    write_json(resources_root() / CURRENT_ACTIVITY_FILE, {"activity": activity_name})


def get_current_activity() -> Optional[str]:
    global CURRENT_ACTIVITY
    if CURRENT_ACTIVITY:
        return CURRENT_ACTIVITY
    data = read_json(resources_root() / CURRENT_ACTIVITY_FILE, {})
    value = data.get("activity")
    if isinstance(value, str) and value in get_activities():
        CURRENT_ACTIVITY = value
    return CURRENT_ACTIVITY


def create_activity(name: str) -> Path:
    cleaned = safe_activity_name(name)
    if not cleaned:
        raise ValueError("活动名称不能为空，且不能只包含非法字符。")
    path = resources_root() / cleaned
    if path.exists():
        raise FileExistsError(f"活动已存在：{cleaned}")
    path.mkdir(parents=True)
    return path


def delete_activity(name: str) -> None:
    path = activity_path(name)
    if path.exists():
        shutil.rmtree(path)


def split_counselor_base(base_name: str) -> tuple[str, str]:
    if "-" not in base_name:
        return base_name, ""
    name, employee_id = base_name.rsplit("-", 1)
    return name, employee_id


def get_counselors(activity_path: Path) -> list[Counselor]:
    result: list[Counselor] = []
    if not activity_path.exists():
        return result
    excel_files = sorted(list(activity_path.glob("*.xls")) + list(activity_path.glob("*.xlsx")))
    for excel in excel_files:
        base = excel.stem
        photos_dir = activity_path / base
        if not photos_dir.is_dir():
            continue
        name, employee_id = split_counselor_base(base)
        result.append(Counselor(name=name, employee_id=employee_id, base_name=base, excel_path=excel, photos_dir=photos_dir))
    return result


def authenticate_admin(username: str, password: str) -> bool:
    cfg = read_json(resources_root() / ADMIN_CONFIG, DEFAULT_ADMIN)
    return username == cfg.get("username") and password == cfg.get("password")


def authenticate_counselor(activity_path: Path, name: str, pwd: str) -> Optional[Counselor]:
    for counselor in get_counselors(activity_path):
        if counselor.name == name.strip() and counselor.employee_id == pwd.strip():
            return counselor
    return None


def read_excel(excel_path: Path) -> pd.DataFrame:
    if excel_path.suffix.lower() == ".xls":
        return pd.read_excel(excel_path, engine="xlrd", dtype=str).fillna("")
    return pd.read_excel(excel_path, engine="openpyxl", dtype=str).fillna("")


def clean_cell(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    stripped_columns = {str(col).strip(): col for col in df.columns}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in stripped_columns:
                mapping[stripped_columns[alias]] = canonical
                break
    return df.rename(columns=mapping)


def validate_excel_columns(excel_path: Path) -> list[str]:
    df = normalize_columns(read_excel(excel_path))
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


def find_photo(photos_dir: Path, student_id: str) -> Optional[Path]:
    sid = str(student_id).strip()
    for suffix in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
        candidate = photos_dir / f"{sid}{suffix}"
        if candidate.exists():
            return candidate
    return None


def load_students(excel_path: Path, photos_dir: Path) -> list[Student]:
    df = normalize_columns(read_excel(excel_path))
    students: list[Student] = []
    counselor_id = excel_path.stem
    for _, row in df.iterrows():
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        if not any(extra.values()):
            continue
        student_id = clean_cell(row.get("学号", ""))
        name = clean_cell(row.get("姓名", ""))
        photo_path = find_photo(photos_dir, student_id)
        students.append(
            Student(
                student_id=student_id,
                name=name,
                major=clean_cell(row.get("专业", "")),
                political_status=clean_cell(row.get("政治面貌", "")),
                position=clean_cell(row.get("担任职务", "")),
                hometown=clean_cell(row.get("家庭住址", "")),
                dormitory=clean_cell(row.get("宿舍", "")),
                financial_status=clean_cell(row.get("家庭经济状况", "")),
                mental_health=clean_cell(row.get("心理健康状况", "")),
                cet_status=clean_cell(row.get("英语四六级", "")),
                failed_courses=clean_cell(row.get("不及格科目", "")),
                awards=clean_cell(row.get("奖惩情况", "")),
                photo_path=photo_path,
                counselor_id=counselor_id,
                extra=extra,
            )
        )
    return students


def load_all_students_for_judge(activity_path: Path, counselor_id_list: Iterable[str]) -> list[Student]:
    ids = set(counselor_id_list)
    result: list[Student] = []
    for counselor in get_counselors(activity_path):
        if counselor.id in ids:
            result.extend(load_students(counselor.excel_path, counselor.photos_dir))
    return result


def validate_counselor_pair(activity_path: Path, base_name: str) -> tuple[bool, list[str], list[str]]:
    excel = activity_path / f"{base_name}.xls"
    if not excel.exists():
        excel = activity_path / f"{base_name}.xlsx"
    photos_dir = activity_path / base_name
    errors: list[str] = []
    warnings: list[str] = []
    if not excel.exists():
        errors.append(f"缺少 Excel：{base_name}.xls/.xlsx")
        return False, errors, warnings
    if not photos_dir.is_dir():
        errors.append(f"缺少照片文件夹：{base_name}")
        return False, errors, warnings
    missing_columns = validate_excel_columns(excel)
    if missing_columns:
        errors.append(f"{base_name} Excel 缺少列：{', '.join(missing_columns)}")
    for student in load_students(excel, photos_dir):
        if student.student_id and student.photo_path is None:
            warnings.append(f"{base_name} 学号 {student.student_id} 缺少照片")
    return not errors, errors, warnings


def decode_zip_member_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        raw_name = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for encoding in ("gbk", "cp936", "utf-8"):
        try:
            decoded = raw_name.decode(encoding)
        except UnicodeDecodeError:
            continue
        if decoded:
            return decoded
    return info.filename


def normalize_zip_member_name(member: str) -> str:
    return member.replace("\\", "/")


def is_safe_zip_member(member: str) -> bool:
    normalized = normalize_zip_member_name(member)
    path = PurePosixPath(normalized)
    if path.is_absolute():
        return False
    if "\x00" in normalized:
        return False
    return ".." not in path.parts and not any(":" in part for part in path.parts)


def clear_activity_counselor_data(activity_path: Path) -> None:
    for excel in list(activity_path.glob("*.xls")) + list(activity_path.glob("*.xlsx")):
        excel.unlink()
    for path in activity_path.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            shutil.rmtree(path)
    score_file = scores_path(activity_path)
    if score_file.exists():
        score_file.unlink()
    attempts_file = attempts_path(activity_path)
    if attempts_file.exists():
        attempts_file.unlink()
    save_contest_counselors(activity_path, [])


def upload_zip(
    zip_path: Path,
    activity_path: Path,
    overwrite: bool = False,
    replace_existing: bool = False,
) -> dict[str, list[str]]:
    ensure_dir(activity_path)
    report = {"imported": [], "skipped": [], "warnings": [], "errors": []}
    with zipfile.ZipFile(zip_path) as zf:
        members = [(info, normalize_zip_member_name(decode_zip_member_name(info))) for info in zf.infolist()]
        unsafe = [name for _, name in members if not is_safe_zip_member(name)]
        if unsafe:
            raise ValueError(f"压缩包包含不安全路径：{unsafe[0]}")
        names = [PurePosixPath(name) for info, name in members if not info.is_dir()]
        root_parts = [p.parts[0] for p in names if len(p.parts) >= 2]
        strip_root = len(set(root_parts)) == 1 and not any(len(p.parts) == 1 for p in names)
        tmp = activity_path / ".upload_tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        try:
            for info, decoded_name in members:
                if info.is_dir():
                    continue
                rel_posix = PurePosixPath(decoded_name)
                if strip_root and len(rel_posix.parts) > 1:
                    rel_posix = PurePosixPath(*rel_posix.parts[1:])
                rel = Path(*rel_posix.parts)
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

            excel_bases = {p.stem for p in list(tmp.glob("*.xls")) + list(tmp.glob("*.xlsx"))}
            folder_bases = {p.name for p in tmp.iterdir() if p.is_dir()}
            complete_bases: list[tuple[str, Path, Path]] = []
            for base in sorted(excel_bases | folder_bases):
                excel = next((tmp / f"{base}{suffix}" for suffix in (".xls", ".xlsx") if (tmp / f"{base}{suffix}").exists()), None)
                folder = tmp / base
                if not excel or not folder.is_dir():
                    report["errors"].append(f"{base} 缺少同名 Excel 或照片文件夹")
                    continue
                complete_bases.append((base, excel, folder))
            if replace_existing and complete_bases:
                clear_activity_counselor_data(activity_path)
            for base, excel, folder in complete_bases:
                if (activity_path / excel.name).exists() or (activity_path / base).exists():
                    if not overwrite:
                        report["skipped"].append(base)
                        continue
                    if (activity_path / excel.name).exists():
                        (activity_path / excel.name).unlink()
                    if (activity_path / base).exists():
                        shutil.rmtree(activity_path / base)
                shutil.move(str(excel), str(activity_path / excel.name))
                shutil.move(str(folder), str(activity_path / base))
                report["imported"].append(base)
                ok, errors, warnings = validate_counselor_pair(activity_path, base)
                report["warnings"].extend(warnings)
                if not ok:
                    report["errors"].extend(errors)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
    return report


def write_zip_file_utf8(zf: zipfile.ZipFile, source: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname.replace("\\", "/"))
    info.date_time = datetime.fromtimestamp(source.stat().st_mtime).timetuple()[:6]
    info.compress_type = zipfile.ZIP_DEFLATED
    info.flag_bits |= 0x800
    with source.open("rb") as src:
        zf.writestr(info, src.read())


def export_all_data_package(destination: Path) -> Path:
    root = resources_root()
    ensure_dir(destination.parent)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                arcname = f"resources/{path.relative_to(root).as_posix()}"
                write_zip_file_utf8(zf, path, arcname)
    return destination


def import_data_package(zip_path: Path, overwrite: bool = True) -> dict[str, list[str]]:
    root = resources_root()
    ensure_dir(root)
    report = {"imported": [], "skipped": [], "warnings": [], "errors": []}
    with zipfile.ZipFile(zip_path) as zf:
        members = [(info, normalize_zip_member_name(decode_zip_member_name(info))) for info in zf.infolist()]
        unsafe = [name for _, name in members if not is_safe_zip_member(name)]
        if unsafe:
            raise ValueError(f"压缩包包含不安全路径：{unsafe[0]}")
        for info, name in members:
            if info.is_dir():
                continue
            parts = PurePosixPath(name).parts
            if not parts:
                continue
            if parts[0] == "resources":
                rel_parts = parts[1:]
            else:
                rel_parts = parts
            if not rel_parts:
                continue
            target = root.joinpath(*rel_parts)
            if target.exists() and not overwrite:
                report["skipped"].append(str(target.relative_to(root)))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            report["imported"].append(str(target.relative_to(root)))
    return report


def download_template(destination: Optional[Path] = None) -> Path:
    source = app_root() / "template.zip"
    fallback = bundled_root() / "resources" / "template.zip"
    actual_source = source if source.exists() else fallback if fallback.exists() else None
    if actual_source is None:
        raise FileNotFoundError("未找到 template.zip，也未找到内置模板。")
    if destination is None:
        return actual_source
    copy_file(actual_source, destination)
    return destination


def contest_config_path(activity_path: Path) -> Path:
    return activity_path / CONTEST_CONFIG


def get_contest_counselors(activity_path: Path) -> list[str]:
    data = read_json(contest_config_path(activity_path), {"counselors": []})
    counselors = data.get("counselors", [])
    return counselors if isinstance(counselors, list) else []


def save_contest_counselors(activity_path: Path, counselor_ids: list[str]) -> None:
    write_json(contest_config_path(activity_path), {"counselors": counselor_ids})


def global_contest_settings_path() -> Path:
    return resources_root() / CONTEST_SETTINGS


def get_contest_settings(activity_path: Optional[Path] = None) -> dict:
    settings = DEFAULT_CONTEST_SETTINGS.copy()
    data = read_json(global_contest_settings_path(), {})
    if isinstance(data, dict):
        flat_data = {key: value for key, value in data.items() if key != "activities"}
        settings.update(flat_data)
        activities = data.get("activities", {})
        if isinstance(activities, dict) and len(activities) == 1:
            activity_settings = next(iter(activities.values()))
            if isinstance(activity_settings, dict):
                settings.update(activity_settings)
    fields = settings.get("answer_fields")
    if not isinstance(fields, list) or not fields:
        settings["answer_fields"] = DEFAULT_CONTEST_SETTINGS["answer_fields"]
    rounds = settings.get("enabled_rounds")
    valid_rounds = {"大海捞针", "鱼目混珠", "描述定位"}
    if not isinstance(rounds, list):
        settings["enabled_rounds"] = DEFAULT_CONTEST_SETTINGS["enabled_rounds"]
    else:
        enabled = [round_name for round_name in rounds if round_name in valid_rounds]
        settings["enabled_rounds"] = enabled or DEFAULT_CONTEST_SETTINGS["enabled_rounds"]
    return settings


def save_contest_settings(settings: dict, activity_path: Optional[Path] = None) -> None:
    merged = DEFAULT_CONTEST_SETTINGS.copy()
    merged.update(settings)
    write_json(global_contest_settings_path(), merged)


def scores_path(activity_path: Path) -> Path:
    return activity_path / SCORES_FILE


def attempts_path(activity_path: Path) -> Path:
    return activity_path / ATTEMPTS_FILE


def load_attempts(activity_path: Path) -> dict[str, int]:
    data = read_json(attempts_path(activity_path), {})
    if not isinstance(data, dict):
        return {}
    result: dict[str, int] = {}
    for counselor_id, value in data.items():
        try:
            result[str(counselor_id)] = int(value)
        except (TypeError, ValueError):
            result[str(counselor_id)] = 0
    return result


def record_counselor_attempt(activity_path: Path, counselor_id: str) -> int:
    attempts = load_attempts(activity_path)
    attempts[counselor_id] = attempts.get(counselor_id, 0) + 1
    write_json(attempts_path(activity_path), attempts)
    return attempts[counselor_id]


def load_scores(activity_path: Path) -> dict[str, dict[str, float]]:
    data = read_json(scores_path(activity_path), {})
    return data if isinstance(data, dict) else {}


def save_score(activity_path: Path, counselor_id: str, scores: dict[str, float]) -> None:
    data = load_scores(activity_path)
    data[counselor_id] = scores
    write_json(scores_path(activity_path), data)


def export_scores(activity_path: Path, awards: Optional[dict[str, int]] = None) -> Path:
    data = load_scores(activity_path)
    rows = []
    ranked = sorted(data.items(), key=lambda item: float(item[1].get("总分", 0)), reverse=True)
    award_labels: dict[str, str] = {}
    if awards:
        cursor = 0
        for label in ("一等奖", "二等奖", "三等奖"):
            count = int(awards.get(label, 0))
            for counselor_id, _ in ranked[cursor : cursor + count]:
                award_labels[counselor_id] = label
            cursor += count
    for rank, (counselor_id, scores) in enumerate(ranked, start=1):
        row = {"排名": rank, "辅导员": counselor_id, **scores, "奖项": award_labels.get(counselor_id, "")}
        rows.append(row)
    output = resources_root() / f"{activity_path.name}_成绩汇总.xlsx"
    pd.DataFrame(rows).to_excel(output, index=False)
    return output
