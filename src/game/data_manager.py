from __future__ import annotations

import json
import posixpath
import random
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

import pandas as pd
from openpyxl import load_workbook
try:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage
except Exception:
    QBuffer = QByteArray = QIODevice = Qt = QImage = None

from data.models import Counselor, Student
from utils.helpers import (
    app_root,
    bundled_root,
    copy_file,
    ensure_dir,
    read_json,
    resources_root,
    write_json,
)

ADMIN_CONFIG = "admin_config.json"
CONTEST_CONFIG = "contest_config.json"
CONTEST_SETTINGS = "contest_settings.json"
SCORES_FILE = "scores.json"
ATTEMPTS_FILE = "contest_attempts.json"
CURRENT_ACTIVITY_FILE = ".current_activity.json"
BLACKLIST_SUFFIX = ".blacklist.json"
DEFAULT_ACTIVITY_NAME = "比赛"
IMPORT_LOG_FILE = "import_log.txt"
ROOT_RESOURCE_FILES = {
    ADMIN_CONFIG,
    CONTEST_SETTINGS,
    CURRENT_ACTIVITY_FILE,
    "judge_config.json",
    "ui_config.json",
}

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
BOOTSTRAPPED = False
PHOTO_CACHE_DIR = ".photo_cache"
PHOTO_CACHE_VERSION = 12
PHOTO_ORDER_SCALE = 1_000_000
PHOTO_MAX_IMAGE_SIDE = 640
PHOTO_RESIZE_MIN_BYTES = 200 * 1024
PHOTO_JPEG_QUALITY = 82
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")
PHOTO_COLUMN_ALIASES = {"照片", "图片", "学生照片", "头像", "相片", "电子照片"}
DISPIMG_RE = re.compile(r"(?:_xlfn\.)?DISPIMG\(\s*['\"]([^'\"]+)['\"]", re.I)
CELL_REF_RE = re.compile(r"^([A-Z]+)([0-9]+)$", re.I)
NS_SHEET = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_DRAWING = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
STUDENT_CACHE: dict[tuple[object, ...], list[Student]] = {}


def bootstrap() -> None:
    global BOOTSTRAPPED
    if BOOTSTRAPPED:
        return
    BOOTSTRAPPED = True
    root = ensure_dir(resources_root())
    ensure_default_config(root / ADMIN_CONFIG, DEFAULT_ADMIN)
    if not global_contest_settings_path().exists():
        save_contest_settings(DEFAULT_CONTEST_SETTINGS)
    ensure_single_activity()


def ensure_default_config(path: Path, default: dict[str, str]) -> None:
    if not path.exists():
        write_json(path, default)


def get_activities() -> list[str]:
    ensure_single_activity()
    return [DEFAULT_ACTIVITY_NAME]


def activity_path(activity_name: str) -> Path:
    return resources_root() / DEFAULT_ACTIVITY_NAME


def set_current_activity(activity_name: str) -> None:
    global CURRENT_ACTIVITY
    CURRENT_ACTIVITY = DEFAULT_ACTIVITY_NAME
    write_json(
        resources_root() / CURRENT_ACTIVITY_FILE, {"activity": DEFAULT_ACTIVITY_NAME}
    )


def get_current_activity() -> Optional[str]:
    global CURRENT_ACTIVITY
    if CURRENT_ACTIVITY != DEFAULT_ACTIVITY_NAME:
        CURRENT_ACTIVITY = DEFAULT_ACTIVITY_NAME
    return CURRENT_ACTIVITY


def create_activity(name: str) -> Path:
    path = activity_path(DEFAULT_ACTIVITY_NAME)
    path.mkdir(parents=True)
    return path


def delete_activity(name: str) -> None:
    path = activity_path(DEFAULT_ACTIVITY_NAME)
    if path.exists():
        clear_activity_counselor_data(path)


def ensure_single_activity() -> Path:
    root = resources_root()
    target = ensure_dir(root / DEFAULT_ACTIVITY_NAME)
    legacy = root / "默认活动"
    if legacy.exists() and legacy.is_dir() and legacy != target:
        for source in legacy.iterdir():
            destination = target / source.name
            if destination.exists():
                continue
            shutil.move(str(source), str(destination))
        try:
            legacy.rmdir()
        except OSError:
            pass
    write_json(root / CURRENT_ACTIVITY_FILE, {"activity": DEFAULT_ACTIVITY_NAME})
    return target


def split_counselor_base(base_name: str) -> tuple[str, str]:
    if "-" not in base_name:
        return base_name, ""
    name, employee_id = base_name.rsplit("-", 1)
    return name, employee_id


def get_counselors(activity_path: Path) -> list[Counselor]:
    result: list[Counselor] = []
    if not activity_path.exists():
        return result
    excel_files = sorted(
        list(activity_path.glob("*.xls")) + list(activity_path.glob("*.xlsx"))
    )
    for excel in excel_files:
        base = excel.stem
        photos_dir = activity_path / base
        name, employee_id = split_counselor_base(base)
        result.append(
            Counselor(
                name=name,
                employee_id=employee_id,
                base_name=base,
                excel_path=excel,
                photos_dir=photos_dir,
            )
        )
    return result


def authenticate_admin(username: str, password: str) -> bool:
    cfg = read_json(resources_root() / ADMIN_CONFIG, DEFAULT_ADMIN)
    return username == cfg.get("username") and password == cfg.get("password")


def authenticate_counselor(
    activity_path: Path, name: str, pwd: str
) -> Optional[Counselor]:
    for counselor in get_counselors(activity_path):
        if counselor.name == name.strip() and counselor.employee_id == pwd.strip():
            return counselor
    return None


def read_excel_raw(excel_path: Path) -> pd.DataFrame:
    if excel_path.suffix.lower() == ".xls":
        return pd.read_excel(excel_path, engine="xlrd", dtype=str, header=None).fillna("")
    return pd.read_excel(excel_path, engine="openpyxl", dtype=str, header=None).fillna("")


def read_excel(excel_path: Path) -> pd.DataFrame:
    raw = read_excel_raw(excel_path)
    if raw.empty:
        return raw
    header_index = detect_header_row(raw)
    columns = unique_column_names([clean_cell(value) for value in raw.iloc[header_index].tolist()])
    df = raw.iloc[header_index + 1 :].copy().reset_index(drop=True)
    df.columns = columns
    df.attrs["header_row"] = header_index + 1
    df.attrs["excel_rows"] = [header_index + 2 + index for index in range(len(df.index))]
    return df.fillna("")


def clean_cell(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def raw_cell_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value)
    return "" if text.lower() in {"nan", "nat", "none"} else text


def detect_header_row(raw: pd.DataFrame) -> int:
    best_index = 0
    best_score = -1
    for index, row in raw.iterrows():
        values = [clean_cell(value) for value in row.tolist()]
        if not any(values):
            continue
        matched: set[str] = set()
        for value in values:
            for canonical, aliases in COLUMN_ALIASES.items():
                if value in aliases:
                    matched.add(canonical)
                    break
            if value in PHOTO_COLUMN_ALIASES:
                matched.add("照片")
        score = len(matched) * 2 + (3 if "姓名" in matched else 0) + (2 if "学号" in matched else 0)
        if score > best_score:
            best_index = int(index)
            best_score = score
    return best_index


def unique_column_names(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    result: list[str] = []
    for index, column in enumerate(columns, start=1):
        base = column or f"未命名列{index}"
        count = counts.get(base, 0) + 1
        counts[base] = count
        result.append(base if count == 1 else f"{base}.{count}")
    return result


def dataframe_excel_row(df: pd.DataFrame, position: int) -> int:
    rows = df.attrs.get("excel_rows", [])
    if isinstance(rows, list) and 0 <= position < len(rows):
        try:
            return int(rows[position])
        except (TypeError, ValueError):
            pass
    header_row = int(df.attrs.get("header_row", 1) or 1)
    return header_row + 1 + position


def dataframe_position_for_excel_row(df: pd.DataFrame, excel_row: int) -> Optional[int]:
    rows = df.attrs.get("excel_rows", [])
    if isinstance(rows, list):
        try:
            return rows.index(excel_row)
        except ValueError:
            return None
    header_row = int(df.attrs.get("header_row", 1) or 1)
    position = excel_row - header_row - 1
    return position if 0 <= position < len(df.index) else None


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
    return [] if "姓名" in df.columns else ["姓名"]


def blacklist_path(excel_path: Path) -> Path:
    return excel_path.with_name(f"{excel_path.stem}{BLACKLIST_SUFFIX}")


def student_identity(student_id: str, name: str) -> str:
    return f"{student_id}\t{name.strip()}"


def has_blacklist_name_suffix(value: str) -> bool:
    trailing_count = 0
    for char in reversed(value):
        if char not in {" ", "\u3000"}:
            break
        trailing_count += 1
    return trailing_count >= 5


def read_blacklist(excel_path: Path) -> set[str]:
    data = read_json(blacklist_path(excel_path), [])
    if not isinstance(data, list):
        return set()
    entries: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        student_id = clean_cell(item.get("学号", ""))
        name = clean_cell(item.get("姓名", ""))
        entries.add(student_identity(student_id, name))
    return entries


def write_blacklist_file(excel_path: Path, rows: list[dict[str, str]]) -> None:
    path = blacklist_path(excel_path)
    if rows:
        write_json(path, rows)
    elif path.exists():
        path.unlink()


def generate_blacklist(excel_path: Path) -> list[dict[str, str]]:
    df = normalize_columns(read_excel(excel_path))
    if "姓名" not in df.columns:
        write_blacklist_file(excel_path, [])
        return []
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for position, (_, row) in enumerate(df.iterrows()):
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        if not any(extra.values()):
            continue
        raw_name = raw_cell_text(row.get("姓名", ""))
        if not raw_name or not has_blacklist_name_suffix(raw_name):
            continue
        student_id = clean_cell(row.get("学号", ""))
        name = clean_cell(raw_name)
        identity = student_identity(student_id, name)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            {
                "Excel行号": str(dataframe_excel_row(df, position)),
                "学号": student_id,
                "姓名": name,
            }
        )
    write_blacklist_file(excel_path, rows)
    return rows


def photo_cache_path(excel_path: Path) -> Path:
    return excel_path.parent / PHOTO_CACHE_DIR / excel_path.stem


def safe_photo_stem(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def image_extension(image, data: bytes) -> str:
    suffix = Path(str(getattr(image, "path", ""))).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".bmp"}:
        return suffix
    return image_data_extension(data)


def image_data_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"GIF8"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    return ".png"


def optimized_photo_data(data: bytes, suffix: str) -> tuple[bytes, str]:
    if QImage is None or QByteArray is None or QBuffer is None or QIODevice is None:
        return data, suffix
    image = QImage()
    if not image.loadFromData(data):
        return data, suffix
    width = image.width()
    height = image.height()
    if (
        max(width, height) <= PHOTO_MAX_IMAGE_SIDE
        and len(data) <= PHOTO_RESIZE_MIN_BYTES
    ):
        return data, suffix
    if max(width, height) > PHOTO_MAX_IMAGE_SIDE and Qt is not None:
        image = image.scaled(
            PHOTO_MAX_IMAGE_SIDE,
            PHOTO_MAX_IMAGE_SIDE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    has_alpha = bool(image.hasAlphaChannel())
    output_format = "PNG" if suffix.lower() == ".png" and has_alpha else "JPG"
    output_suffix = ".png" if output_format == "PNG" else ".jpg"
    output = QByteArray()
    buffer = QBuffer(output)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return data, suffix
    try:
        quality = -1 if output_format == "PNG" else PHOTO_JPEG_QUALITY
        if not image.save(buffer, output_format, quality):
            return data, suffix
    finally:
        buffer.close()
    optimized = bytes(output)
    if not optimized or len(optimized) >= len(data):
        return data, suffix
    return optimized, output_suffix


def image_anchor_marker(image, attr: str):
    return getattr(getattr(image, "anchor", None), attr, None)


def image_anchor_row(image) -> Optional[int]:
    marker = image_anchor_marker(image, "_from")
    row = getattr(marker, "row", None)
    if row is None:
        return None
    return int(row) + 1


def image_anchor_col(image) -> Optional[int]:
    marker = image_anchor_marker(image, "_from")
    col = getattr(marker, "col", None)
    if col is None:
        return None
    return int(col) + 1


def image_anchor_row_center(image) -> Optional[float]:
    start = image_anchor_marker(image, "_from")
    end = image_anchor_marker(image, "to")
    start_row = getattr(start, "row", None)
    if start_row is None:
        return None
    end_row = getattr(end, "row", None)
    if end_row is None:
        return float(int(start_row) + 1)
    start_offset = getattr(start, "rowOff", 0) or 0
    end_offset = getattr(end, "rowOff", 0) or 0
    # EMU offsets are row-local. Keep only their relative position so a picture
    # anchored across rows maps to the row containing its visual center.
    start_pos = int(start_row) + float(start_offset) / 9_525_000
    end_pos = int(end_row) + float(end_offset) / 9_525_000
    return ((start_pos + end_pos) / 2) + 1


def image_anchor_col_center(image) -> Optional[float]:
    start = image_anchor_marker(image, "_from")
    end = image_anchor_marker(image, "to")
    start_col = getattr(start, "col", None)
    if start_col is None:
        return None
    end_col = getattr(end, "col", None)
    if end_col is None:
        return float(int(start_col) + 1)
    start_offset = getattr(start, "colOff", 0) or 0
    end_offset = getattr(end, "colOff", 0) or 0
    start_pos = int(start_col) + float(start_offset) / 9_525_000
    end_pos = int(end_col) + float(end_offset) / 9_525_000
    return ((start_pos + end_pos) / 2) + 1


def student_excel_rows(df: pd.DataFrame) -> set[int]:
    rows: set[int] = set()
    for position, (_, row) in enumerate(df.iterrows()):
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        if any(extra.values()):
            rows.add(dataframe_excel_row(df, position))
    return rows


def student_photo_slots(df: pd.DataFrame) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = []
    for position, (_, row) in enumerate(df.iterrows()):
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        slots.append(
            {
                "excel_row": dataframe_excel_row(df, position),
                "student_id": clean_cell(row.get("学号", "")),
                "has_student": any(extra.values()),
            }
        )
    return slots


def photo_excel_columns(df: pd.DataFrame) -> set[int]:
    columns: set[int] = set()
    for index, column in enumerate(df.columns, start=1):
        if str(column).strip() in PHOTO_COLUMN_ALIASES:
            columns.add(index)
    return columns


def nearest_student_row(center: Optional[float], valid_rows: set[int]) -> Optional[int]:
    if center is None or not valid_rows:
        return None
    nearest = min(valid_rows, key=lambda row: abs(row - center))
    return nearest if abs(nearest - center) <= 1.25 else None


def nearest_photo_column(center: Optional[float], valid_columns: set[int]) -> Optional[int]:
    if center is None or not valid_columns:
        return None
    nearest = min(valid_columns, key=lambda column: abs(column - center))
    return nearest if abs(nearest - center) <= 1.25 else None


def image_sort_key(image) -> int:
    center = image_anchor_row_center(image)
    if center is not None:
        return int(center * 1000)
    return int((image_anchor_row(image) or 0) * 1000)


def image_item_sort_key(item: dict) -> tuple[int, int]:
    order = item.get("order")
    if not isinstance(order, int):
        order = 0
    return order, image_item_z_order(item)


def image_item_z_order(item: dict) -> int:
    z_order = item.get("z_order")
    if isinstance(z_order, int):
        return z_order
    order = item.get("order")
    return int(order) if isinstance(order, (float, int)) else 0


def xlsx_part_rels_path(part_path: str) -> str:
    return posixpath.join(
        posixpath.dirname(part_path), "_rels", f"{posixpath.basename(part_path)}.rels"
    )


def resolve_xlsx_target(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return posixpath.normpath(target.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def xlsx_relationships(
    zf: zipfile.ZipFile, part_path: str
) -> dict[str, tuple[str, str]]:
    rels_path = xlsx_part_rels_path(part_path)
    if rels_path not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_path))
    relationships: dict[str, tuple[str, str]] = {}
    for rel in root:
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        rel_type = rel.attrib.get("Type", "")
        if not rel_id or not target or rel.attrib.get("TargetMode") == "External":
            continue
        relationships[rel_id] = (resolve_xlsx_target(part_path, target), rel_type)
    return relationships


def worksheet_part_path(zf: zipfile.ZipFile, worksheet) -> str:
    path = str(getattr(worksheet, "path", "")).lstrip("/")
    if path in zf.namelist():
        return path
    worksheet_parts = sorted(
        name
        for name in zf.namelist()
        if name.startswith("xl/worksheets/") and name.endswith(".xml")
    )
    return worksheet_parts[0] if worksheet_parts else ""


def drawing_anchor_position(
    anchor,
) -> tuple[Optional[int], Optional[float], Optional[int], Optional[float]]:
    marker = anchor.find("xdr:from", NS_DRAWING)
    if marker is None:
        return None, None, None, None
    row_text = marker.findtext("xdr:row", namespaces=NS_DRAWING)
    col_text = marker.findtext("xdr:col", namespaces=NS_DRAWING)
    if row_text is None or col_text is None:
        return None, None, None, None
    start_row = int(row_text)
    start_col = int(col_text)
    start_offset_text = marker.findtext(
        "xdr:rowOff", default="0", namespaces=NS_DRAWING
    )
    start_col_offset_text = marker.findtext(
        "xdr:colOff", default="0", namespaces=NS_DRAWING
    )
    start_offset = int(start_offset_text or 0)
    start_col_offset = int(start_col_offset_text or 0)
    end_marker = anchor.find("xdr:to", NS_DRAWING)
    if end_marker is None:
        return start_row + 1, float(start_row + 1), start_col + 1, float(start_col + 1)
    end_row_text = end_marker.findtext("xdr:row", namespaces=NS_DRAWING)
    end_col_text = end_marker.findtext("xdr:col", namespaces=NS_DRAWING)
    if end_row_text is None or end_col_text is None:
        return start_row + 1, float(start_row + 1), start_col + 1, float(start_col + 1)
    end_row = int(end_row_text)
    end_col = int(end_col_text)
    end_offset_text = end_marker.findtext(
        "xdr:rowOff", default="0", namespaces=NS_DRAWING
    )
    end_col_offset_text = end_marker.findtext(
        "xdr:colOff", default="0", namespaces=NS_DRAWING
    )
    end_offset = int(end_offset_text or 0)
    end_col_offset = int(end_col_offset_text or 0)
    start_pos = start_row + float(start_offset) / 9_525_000
    end_pos = end_row + float(end_offset) / 9_525_000
    start_col_pos = start_col + float(start_col_offset) / 9_525_000
    end_col_pos = end_col + float(end_col_offset) / 9_525_000
    return (
        start_row + 1,
        ((start_pos + end_pos) / 2) + 1,
        start_col + 1,
        ((start_col_pos + end_col_pos) / 2) + 1,
    )


def raw_xlsx_image_items(excel_path: Path, worksheet) -> list[dict]:
    items: list[dict] = []
    with zipfile.ZipFile(excel_path) as zf:
        sheet_part = worksheet_part_path(zf, worksheet)
        if not sheet_part:
            return items
        sheet_rels = xlsx_relationships(zf, sheet_part)
        drawing_parts = [
            target
            for target, rel_type in sheet_rels.values()
            if rel_type.endswith("/drawing")
        ]
        z_order = 0
        for drawing_part in drawing_parts:
            if drawing_part not in zf.namelist():
                continue
            drawing_rels = xlsx_relationships(zf, drawing_part)
            root = ET.fromstring(zf.read(drawing_part))
            for anchor in root:
                if not str(anchor.tag).endswith("Anchor"):
                    continue
                anchor_z_order = z_order
                z_order += 1
                blip = anchor.find(".//a:blip", NS_DRAWING)
                if blip is None:
                    continue
                rel_id = blip.attrib.get(f"{OFFICE_REL_NS}embed") or blip.attrib.get(
                    f"{OFFICE_REL_NS}link"
                )
                if not rel_id or rel_id not in drawing_rels:
                    continue
                media_part, rel_type = drawing_rels[rel_id]
                if not rel_type.endswith("/image") or media_part not in zf.namelist():
                    continue
                data = zf.read(media_part)
                if not data:
                    continue
                anchor_row, center, anchor_col, col_center = drawing_anchor_position(anchor)
                suffix = Path(media_part).suffix.lower() or image_data_extension(data)
                row_order = int((center or anchor_row or anchor_z_order) * 1000)
                order_key = row_order * PHOTO_ORDER_SCALE + anchor_z_order
                items.append(
                    {
                        "order": order_key,
                        "z_order": anchor_z_order,
                        "center": center,
                        "anchor_row": anchor_row,
                        "col_center": col_center,
                        "anchor_col": anchor_col,
                        "data": data,
                        "suffix": suffix,
                    }
                )
    return items


def wps_dispimg_id(value: object) -> Optional[str]:
    text = clean_cell(value)
    if not text:
        return None
    match = DISPIMG_RE.search(text)
    return match.group(1) if match else None


def excel_column_number(letters: str) -> int:
    number = 0
    for char in letters.upper():
        if not "A" <= char <= "Z":
            return 0
        number = number * 26 + (ord(char) - ord("A") + 1)
    return number


def cell_reference_position(reference: str) -> Optional[tuple[int, int]]:
    match = CELL_REF_RE.match(str(reference))
    if not match:
        return None
    column = excel_column_number(match.group(1))
    row = int(match.group(2))
    if row <= 0 or column <= 0:
        return None
    return row, column


def wps_sheet_dispimg_ids(excel_path: Path, worksheet) -> dict[tuple[int, int], str]:
    ids: dict[tuple[int, int], str] = {}
    with zipfile.ZipFile(excel_path) as zf:
        sheet_part = worksheet_part_path(zf, worksheet)
        if not sheet_part or sheet_part not in zf.namelist():
            return ids
        root = ET.fromstring(zf.read(sheet_part))
        for cell in root.findall(".//main:c", NS_SHEET):
            position = cell_reference_position(cell.attrib.get("r", ""))
            if position is None:
                continue
            formula = cell.findtext("main:f", default="", namespaces=NS_SHEET)
            value = cell.findtext("main:v", default="", namespaces=NS_SHEET)
            image_id = wps_dispimg_id(formula) or wps_dispimg_id(value)
            if image_id:
                ids[position] = image_id
    return ids


def wps_cell_image_map(excel_path: Path) -> dict[str, tuple[bytes, str, int]]:
    images: dict[str, tuple[bytes, str, int]] = {}
    with zipfile.ZipFile(excel_path) as zf:
        cellimage_parts = [
            name
            for name in zf.namelist()
            if name.endswith("cellimages.xml") and not name.endswith(".rels")
        ]
        for cellimage_part in sorted(cellimage_parts):
            rels = xlsx_relationships(zf, cellimage_part)
            root = ET.fromstring(zf.read(cellimage_part))
            for z_order, pic in enumerate(root.findall(".//xdr:pic", NS_DRAWING)):
                name_node = pic.find(".//xdr:cNvPr", NS_DRAWING)
                image_id = name_node.attrib.get("name") if name_node is not None else ""
                if not image_id:
                    continue
                blip = pic.find(".//a:blip", NS_DRAWING)
                if blip is None:
                    continue
                rel_id = blip.attrib.get(f"{OFFICE_REL_NS}embed") or blip.attrib.get(
                    f"{OFFICE_REL_NS}link"
                )
                if not rel_id or rel_id not in rels:
                    continue
                media_part, rel_type = rels[rel_id]
                if not rel_type.endswith("/image") or media_part not in zf.namelist():
                    continue
                data = zf.read(media_part)
                if not data:
                    continue
                suffix = Path(media_part).suffix.lower() or image_data_extension(data)
                images[image_id] = (data, suffix, z_order)
    return images


def wps_cell_image_items(excel_path: Path, worksheet, df: pd.DataFrame) -> list[dict]:
    image_map = wps_cell_image_map(excel_path)
    if not image_map:
        return []

    columns = list(df.columns)
    photo_columns = photo_excel_columns(df) or set(range(1, len(columns) + 1))
    sheet_image_ids = wps_sheet_dispimg_ids(excel_path, worksheet)
    items: list[dict] = []
    for position, (_, row) in enumerate(df.iterrows()):
        excel_row = dataframe_excel_row(df, position)
        for column_index in sorted(photo_columns):
            if column_index < 1 or column_index > len(columns):
                continue
            image_id = wps_dispimg_id(row.get(columns[column_index - 1], ""))
            if not image_id:
                image_id = sheet_image_ids.get((excel_row, column_index))
            if not image_id or image_id not in image_map:
                continue
            data, suffix, z_order = image_map[image_id]
            row_order = int(excel_row * 1000)
            items.append(
                {
                    "order": row_order * PHOTO_ORDER_SCALE + z_order,
                    "z_order": z_order,
                    "center": float(excel_row),
                    "anchor_row": excel_row,
                    "col_center": float(column_index),
                    "anchor_col": column_index,
                    "data": data,
                    "suffix": suffix,
                }
            )
    return items


def cache_marker(excel_path: Path) -> dict[str, object]:
    stat = excel_path.stat()
    return {
        "photo_cache_version": PHOTO_CACHE_VERSION,
        "excel": excel_path.name,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def load_cached_excel_photos(excel_path: Path) -> Optional[dict[int, Path]]:
    cache_dir = photo_cache_path(excel_path)
    marker_path = cache_dir / "manifest.json"
    data = read_json(marker_path, {})
    if not isinstance(data, dict):
        return None
    current = cache_marker(excel_path)
    if any(data.get(key) != value for key, value in current.items()):
        return None
    rows = data.get("rows", {})
    if not isinstance(rows, dict):
        return None
    result: dict[int, Path] = {}
    for row, filename in rows.items():
        try:
            row_number = int(row)
        except (TypeError, ValueError):
            continue
        if not isinstance(filename, str):
            continue
        path = cache_dir / filename
        if not path.exists():
            return None
        result[row_number] = path
    return result


def photo_cache_manifest(excel_path: Path) -> dict:
    data = read_json(photo_cache_path(excel_path) / "manifest.json", {})
    if not isinstance(data, dict):
        return {}
    current = cache_marker(excel_path)
    if any(data.get(key) != value for key, value in current.items()):
        return {}
    return data


def photo_import_summary(excel_path: Path, base_name: str) -> Optional[str]:
    if excel_path.suffix.lower() != ".xlsx":
        return None
    data = photo_cache_manifest(excel_path)
    rows = data.get("rows", {})
    if not isinstance(rows, dict):
        return None
    strategy = data.get("photo_strategy", "")
    photo_count = data.get("photo_count", "?")
    student_row_count = data.get("student_row_count", "?")
    photo_source = data.get("photo_source", "")
    labels = {
        "anchor": "锚点匹配",
        "photo_column_anchor": "照片列锚点匹配",
        "order": "顺序匹配",
        "student_index": "学生列表编号匹配",
    }
    label = labels.get(str(strategy), str(strategy) or "未知策略")
    source_labels = {
        "openpyxl": "常规读取",
        "raw": "底层解包",
        "wps_cellimage": "WPS单元格图片",
    }
    source_label = source_labels.get(str(photo_source), str(photo_source) or "未知来源")
    return f"{base_name} 照片导入采用{source_label}+{label}，读取 {photo_count} 张图片，命中 {len(rows)} / {student_row_count} 行"


def extract_excel_photos(excel_path: Path, df: pd.DataFrame) -> dict[int, Path]:
    if excel_path.suffix.lower() != ".xlsx":
        return {}
    cached = load_cached_excel_photos(excel_path)
    if cached is not None:
        return cached

    cache_dir = photo_cache_path(excel_path)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    workbook = load_workbook(excel_path, data_only=True)
    try:
        worksheet = workbook.active
        valid_rows = student_excel_rows(df)
        valid_photo_columns = photo_excel_columns(df)
        openpyxl_items = []
        for z_order, image in enumerate(worksheet._images):
            try:
                data = image._data()
            except Exception:
                continue
            if not data:
                continue
            row_order = image_sort_key(image)
            openpyxl_items.append(
                {
                    "order": row_order * PHOTO_ORDER_SCALE + z_order,
                    "z_order": z_order,
                    "center": image_anchor_row_center(image),
                    "anchor_row": image_anchor_row(image),
                    "col_center": image_anchor_col_center(image),
                    "anchor_col": image_anchor_col(image),
                    "data": data,
                    "suffix": image_extension(image, data),
                }
            )
        raw_items = raw_xlsx_image_items(excel_path, worksheet)
        wps_items = wps_cell_image_items(excel_path, worksheet, df)
        candidates = []
        for source, items in (
            ("openpyxl", openpyxl_items),
            ("raw", raw_items),
            ("wps_cellimage", wps_items),
        ):
            candidate_rows, candidate_strategy = best_photo_rows(
                items, df, valid_photo_columns
            )
            candidates.append((source, items, candidate_rows, candidate_strategy))
        photo_source, image_items, photo_rows, photo_strategy = max(
            candidates,
            key=lambda item: (*photo_match_score(item[2], valid_rows), len(item[1])),
        )
        rows = write_photo_rows(cache_dir, df, photo_rows)
    finally:
        workbook.close()

    manifest = cache_marker(excel_path)
    manifest["rows"] = rows
    manifest["photo_strategy"] = photo_strategy
    manifest["photo_source"] = photo_source
    manifest["photo_count"] = len(image_items)
    manifest["student_row_count"] = len(valid_rows)
    manifest["student_slot_count"] = len(student_photo_slots(df))
    manifest["photo_column_count"] = len(valid_photo_columns)
    write_json(cache_dir / "manifest.json", manifest)
    return {int(row): cache_dir / filename for row, filename in rows.items()}


def best_photo_rows(
    image_items: list[dict],
    df: pd.DataFrame,
    valid_photo_columns: set[int],
) -> tuple[dict[int, tuple[bytes, str]], str]:
    scoped_items = filter_photo_column_items(image_items, valid_photo_columns)
    scoped_items = top_layer_photo_items(scoped_items, df, valid_photo_columns)
    indexed_rows = match_photos_by_student_index(scoped_items, df)
    if indexed_rows or scoped_items:
        return indexed_rows, "student_index"
    return {}, "student_index"


def photo_match_score(
    rows: dict[int, tuple[bytes, str]], valid_rows: set[int]
) -> tuple[int, int]:
    return (len(set(rows) & valid_rows), -abs(len(rows) - len(valid_rows)))


def filter_photo_column_items(
    image_items: list[dict], valid_photo_columns: set[int]
) -> list[dict]:
    if not valid_photo_columns:
        return image_items
    result = []
    for item in image_items:
        column = (
            nearest_photo_column(item.get("col_center"), valid_photo_columns)
            or item.get("anchor_col")
        )
        if column in valid_photo_columns:
            result.append(item)
    return result


def image_item_photo_column(
    item: dict, valid_photo_columns: set[int]
) -> Optional[int]:
    column = nearest_photo_column(item.get("col_center"), valid_photo_columns)
    if isinstance(column, int):
        return column
    anchor_col = item.get("anchor_col")
    if isinstance(anchor_col, int):
        return anchor_col
    col_center = item.get("col_center")
    if isinstance(col_center, (float, int)):
        return int(round(col_center))
    return None


def match_photos_by_anchor(
    image_items: list[dict], valid_rows: set[int]
) -> dict[int, tuple[bytes, str]]:
    rows: dict[int, tuple[bytes, str]] = {}
    row_z_orders: dict[int, int] = {}
    for item in image_items:
        row_number = (
            nearest_student_row(item["center"], valid_rows) or item["anchor_row"]
        )
        if (
            row_number is None
            or row_number <= 1
            or row_number not in valid_rows
        ):
            continue
        z_order = image_item_z_order(item)
        if row_number in rows and z_order < row_z_orders.get(row_number, 0):
            continue
        rows[row_number] = (item["data"], item["suffix"])
        row_z_orders[row_number] = z_order
    return rows


def image_item_excel_row(item: dict, slot_rows: set[int]) -> Optional[int]:
    anchor_row = item.get("anchor_row")
    if isinstance(anchor_row, int) and anchor_row in slot_rows:
        return anchor_row
    center = item.get("center")
    if isinstance(center, (float, int)):
        row_number = int(center)
        if row_number in slot_rows:
            return row_number
    return None


def top_layer_photo_items(
    image_items: list[dict], df: pd.DataFrame, valid_photo_columns: set[int]
) -> list[dict]:
    slots = student_photo_slots(df)
    slot_rows = {int(slot["excel_row"]) for slot in slots}
    if not slot_rows:
        return image_items

    top_by_slot: dict[tuple[int, Optional[int]], dict] = {}
    unassigned_items: list[dict] = []
    for item in image_items:
        row_number = image_item_excel_row(item, slot_rows)
        if row_number is None:
            unassigned_items.append(item)
            continue
        column = image_item_photo_column(item, valid_photo_columns)
        key = (row_number, column)
        current = top_by_slot.get(key)
        if current is None or image_item_z_order(item) >= image_item_z_order(current):
            top_by_slot[key] = item

    return sorted(
        [*unassigned_items, *top_by_slot.values()],
        key=image_item_sort_key,
    )


def match_photos_by_student_index(
    image_items: list[dict], df: pd.DataFrame
) -> dict[int, tuple[bytes, str]]:
    rows: dict[int, tuple[bytes, str]] = {}
    row_z_orders: dict[int, int] = {}
    slots = student_photo_slots(df)
    if not slots:
        return rows

    slot_by_row = {int(slot["excel_row"]): slot for slot in slots}
    slot_rows = set(slot_by_row)
    sorted_items = sorted(image_items, key=image_item_sort_key)
    unresolved_items: list[dict] = []
    for item in sorted_items:
        row_number = image_item_excel_row(item, slot_rows)
        if row_number is None:
            unresolved_items.append(item)
            continue
        slot = slot_by_row[row_number]
        if not slot["has_student"]:
            continue
        z_order = image_item_z_order(item)
        if row_number in rows and z_order < row_z_orders.get(row_number, 0):
            continue
        rows[row_number] = (item["data"], item["suffix"])
        row_z_orders[row_number] = z_order

    if rows or not unresolved_items:
        return rows

    for slot, item in zip(slots, unresolved_items):
        row_number = int(slot["excel_row"])
        if not slot["has_student"] or row_number in rows:
            continue
        rows[row_number] = (item["data"], item["suffix"])
    return rows


def match_photos_by_order(
    image_items: list[dict], valid_rows: set[int], allow_partial: bool = True
) -> dict[int, tuple[bytes, str]]:
    rows: dict[int, tuple[bytes, str]] = {}
    if not allow_partial and len(image_items) != len(valid_rows):
        return rows
    sorted_items = sorted(image_items, key=image_item_sort_key)
    for row_number, item in zip(sorted(valid_rows), sorted_items):
        rows[row_number] = (item["data"], item["suffix"])
    return rows


def write_photo_rows(
    cache_dir: Path,
    df: pd.DataFrame,
    photo_rows: dict[int, tuple[bytes, str]],
) -> dict[int, str]:
    row_counts: dict[int, int] = {}
    rows: dict[int, str] = {}
    for row_number, (data, suffix) in sorted(photo_rows.items()):
        save_excel_photo(cache_dir, df, row_counts, rows, row_number, data, suffix)
    return rows


def save_excel_photo(
    cache_dir: Path,
    df: pd.DataFrame,
    row_counts: dict[int, int],
    rows: dict[int, str],
    row_number: int,
    data: bytes,
    suffix: str,
) -> None:
    df_index = dataframe_position_for_excel_row(df, row_number)
    if df_index is not None and 0 <= df_index < len(df.index):
        student_id = clean_cell(df.iloc[df_index].get("学号", ""))
    else:
        student_id = ""
    count = row_counts.get(row_number, 0) + 1
    row_counts[row_number] = count
    data, suffix = optimized_photo_data(data, suffix)
    stem = safe_photo_stem(student_id, f"row_{row_number}")
    filename = f"{stem}{suffix}" if count == 1 else f"{stem}_{count}{suffix}"
    target = cache_dir / filename
    target.write_bytes(data)
    rows[row_number] = filename


def find_photo(photos_dir: Path, student_id: str) -> Optional[Path]:
    sid = str(student_id).strip()
    if not photos_dir.is_dir():
        return None
    for suffix in PHOTO_SUFFIXES:
        candidate = photos_dir / f"{sid}{suffix}"
        if candidate.exists():
            return candidate
    return None


def file_cache_signature(path: Optional[Path]) -> tuple[str, int, int]:
    if path is None or not path.exists():
        return ("", 0, 0)
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def directory_cache_signature(path: Optional[Path]) -> tuple[str, int, int]:
    if path is None or not path.is_dir():
        return ("", 0, 0)
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, len(list(path.iterdir())))


def load_students_cache_key(
    excel_path: Path, photos_dir: Optional[Path], include_blacklisted: bool
) -> tuple[object, ...]:
    return (
        PHOTO_CACHE_VERSION,
        file_cache_signature(excel_path),
        file_cache_signature(blacklist_path(excel_path)),
        directory_cache_signature(photos_dir),
        include_blacklisted,
    )


def clear_student_cache() -> None:
    STUDENT_CACHE.clear()


def import_log_path(base_path: Path) -> Path:
    return base_path / IMPORT_LOG_FILE


def format_report_entries(title: str, entries: object) -> list[str]:
    if not isinstance(entries, list) or not entries:
        return [f"{title}：无"]
    lines = [f"{title}：{len(entries)}"]
    lines.extend(f"  - {entry}" for entry in entries)
    return lines


def write_import_log(
    log_dir: Path,
    operation: str,
    source_path: Optional[Path],
    report: dict,
) -> Path:
    ensure_dir(log_dir)
    path = import_log_path(log_dir)
    imported = report.get("imported", [])
    skipped = report.get("skipped", [])
    warnings = report.get("warnings", [])
    errors = report.get("errors", [])
    lines = [
        "=" * 72,
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"操作：{operation}",
        f"来源：{source_path if source_path is not None else '无'}",
        f"目标：{log_dir}",
        (
            "摘要："
            f"导入 {len(imported) if isinstance(imported, list) else 0}；"
            f"跳过 {len(skipped) if isinstance(skipped, list) else 0}；"
            f"警告 {len(warnings) if isinstance(warnings, list) else 0}；"
            f"错误 {len(errors) if isinstance(errors, list) else 0}"
        ),
        "",
    ]
    lines.extend(format_report_entries("导入", imported))
    lines.extend(format_report_entries("跳过", skipped))
    lines.extend(format_report_entries("警告", warnings))
    lines.extend(format_report_entries("错误", errors))
    lines.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        handle.write("\n")
    report["log_path"] = str(path)
    return path


def load_students(
    excel_path: Path,
    photos_dir: Optional[Path] = None,
    include_blacklisted: bool = False,
) -> list[Student]:
    cache_key = load_students_cache_key(excel_path, photos_dir, include_blacklisted)
    cached = STUDENT_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    df = normalize_columns(read_excel(excel_path))
    photos_by_row = extract_excel_photos(excel_path, df)
    students: list[Student] = []
    counselor_id = excel_path.stem
    blacklist = set() if include_blacklisted else read_blacklist(excel_path)
    for position, (_, row) in enumerate(df.iterrows()):
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        if not any(extra.values()):
            continue
        student_id = clean_cell(row.get("学号", ""))
        name = clean_cell(row.get("姓名", ""))
        if student_identity(student_id, name) in blacklist:
            continue
        excel_row = dataframe_excel_row(df, position)
        photo_path = photos_by_row.get(excel_row)
        if photo_path is None and photos_dir is not None:
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
    STUDENT_CACHE[cache_key] = list(students)
    return students


def load_all_students_for_judge(
    activity_path: Path, counselor_id_list: Iterable[str]
) -> list[Student]:
    ids = set(counselor_id_list)
    result: list[Student] = []
    for counselor in get_counselors(activity_path):
        if counselor.id in ids:
            result.extend(load_students(counselor.excel_path, counselor.photos_dir))
    return result


def load_student_sample_for_judge(
    activity_path: Path,
    counselor_id_list: Iterable[str],
    count: int,
    pool_multiplier: int = 4,
) -> list[Student]:
    if count <= 0:
        return []
    ids = set(counselor_id_list)
    counselors = [
        counselor for counselor in get_counselors(activity_path) if counselor.id in ids
    ]
    random.shuffle(counselors)
    target_pool_size = max(count, count * pool_multiplier)
    result: list[Student] = []
    for counselor in counselors:
        result.extend(load_students(counselor.excel_path, counselor.photos_dir))
        if target_pool_size > 0 and len(result) >= target_pool_size:
            break
    if count > 0 and len(result) > count:
        return random.sample(result, count)
    return result


def missing_photo_rows(
    excel_path: Path, photos_dir: Optional[Path] = None
) -> list[int]:
    df = normalize_columns(read_excel(excel_path))
    photos_by_row = extract_excel_photos(excel_path, df)
    rows: list[int] = []
    for position, (_, row) in enumerate(df.iterrows()):
        extra = {str(k): clean_cell(v) for k, v in row.items()}
        if not any(extra.values()):
            continue
        student_id = clean_cell(row.get("学号", ""))
        if not student_id:
            continue
        excel_row = dataframe_excel_row(df, position)
        if photos_by_row.get(excel_row) is None and (
            photos_dir is None or find_photo(photos_dir, student_id) is None
        ):
            rows.append(excel_row)
    return rows


def format_row_numbers(rows: list[int]) -> str:
    if len(rows) <= 20:
        return "、".join(str(row) for row in rows)
    head = "、".join(str(row) for row in rows[:20])
    return f"{head} 等"


def validate_counselor_pair(
    activity_path: Path, base_name: str
) -> tuple[bool, list[str], list[str]]:
    excel = activity_path / f"{base_name}.xls"
    if not excel.exists():
        excel = activity_path / f"{base_name}.xlsx"
    photos_dir = activity_path / base_name
    errors: list[str] = []
    warnings: list[str] = []
    if not excel.exists():
        errors.append(f"缺少 Excel：{base_name}.xls/.xlsx")
        return False, errors, warnings
    missing_columns = validate_excel_columns(excel)
    if missing_columns:
        errors.append(f"{excel.name}：缺少列 {', '.join(missing_columns)}")
    generate_blacklist(excel)
    photo_rows = missing_photo_rows(excel, photos_dir)
    summary = photo_import_summary(excel, base_name)
    if summary:
        warnings.append(summary)
    if photo_rows:
        warnings.append(
            f"{excel.name}：缺少照片，涉及行 {format_row_numbers(photo_rows)}（共 {len(photo_rows)} 行）"
        )
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
    clear_student_cache()
    for excel in list(activity_path.glob("*.xls")) + list(activity_path.glob("*.xlsx")):
        excel.unlink()
    for blacklist in activity_path.glob(f"*{BLACKLIST_SUFFIX}"):
        blacklist.unlink()
    for path in activity_path.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            shutil.rmtree(path)
    cache_dir = activity_path / PHOTO_CACHE_DIR
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
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
    clear_student_cache()
    ensure_dir(activity_path)
    report = {"imported": [], "skipped": [], "warnings": [], "errors": []}
    with zipfile.ZipFile(zip_path) as zf:
        members = [
            (info, normalize_zip_member_name(decode_zip_member_name(info)))
            for info in zf.infolist()
        ]
        unsafe = [name for _, name in members if not is_safe_zip_member(name)]
        if unsafe:
            raise ValueError(f"压缩包包含不安全路径：{unsafe[0]}")
        names = [PurePosixPath(name) for info, name in members if not info.is_dir()]
        root_parts = [p.parts[0] for p in names if len(p.parts) >= 2]
        strip_root = len(set(root_parts)) == 1 and not any(
            len(p.parts) == 1 for p in names
        )
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

            excel_files = sorted(
                [
                    p
                    for p in list(tmp.rglob("*.xls")) + list(tmp.rglob("*.xlsx"))
                    if not p.name.startswith("~$")
                    and not any(part.startswith("__MACOSX") for part in p.parts)
                ]
            )
            complete_bases: list[tuple[str, Path, Optional[Path]]] = []
            seen_bases: set[str] = set()
            for excel in excel_files:
                base = excel.stem
                if base in seen_bases:
                    report["errors"].append(
                        f"{base} 存在重名 Excel，请修改文件名后重新导入"
                    )
                    continue
                seen_bases.add(base)
                folder = excel.parent / base
                complete_bases.append(
                    (base, excel, folder if folder.is_dir() else None)
                )
            if replace_existing and complete_bases:
                clear_activity_counselor_data(activity_path)
            for base, excel, folder in complete_bases:
                if (activity_path / excel.name).exists() or (
                    activity_path / base
                ).exists():
                    if not overwrite:
                        report["skipped"].append(base)
                        continue
                    if (activity_path / excel.name).exists():
                        (activity_path / excel.name).unlink()
                    old_blacklist = activity_path / f"{base}{BLACKLIST_SUFFIX}"
                    if old_blacklist.exists():
                        old_blacklist.unlink()
                    if (activity_path / base).exists():
                        shutil.rmtree(activity_path / base)
                shutil.move(str(excel), str(activity_path / excel.name))
                if folder is not None:
                    shutil.move(str(folder), str(activity_path / base))
                report["imported"].append(base)
                ok, errors, warnings = validate_counselor_pair(activity_path, base)
                report["warnings"].extend(warnings)
                if not ok:
                    report["errors"].extend(errors)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
    write_import_log(activity_path, "上传资料包", zip_path, report)
    return report


def upload_excel(
    excel_path: Path,
    activity_path: Path,
    overwrite: bool = False,
    replace_existing: bool = False,
) -> dict[str, list[str]]:
    clear_student_cache()
    ensure_dir(activity_path)
    report = {"imported": [], "skipped": [], "warnings": [], "errors": []}
    source_path = excel_path
    if excel_path.suffix.lower() != ".xlsx":
        report["errors"].append(f"{excel_path.name} 不是 .xlsx 文件")
        write_import_log(activity_path, "上传Excel", source_path, report)
        return report
    base = excel_path.stem
    if not base:
        report["errors"].append("Excel 文件名不能为空")
        write_import_log(activity_path, "上传Excel", source_path, report)
        return report
    target = activity_path / excel_path.name
    if excel_path.resolve() == target.resolve():
        temp_source = activity_path / ".upload_tmp" / excel_path.name
        temp_source.parent.mkdir(parents=True, exist_ok=True)
        copy_file(excel_path, temp_source)
        excel_path = temp_source
    if replace_existing:
        clear_activity_counselor_data(activity_path)
    elif target.exists():
        if not overwrite:
            report["skipped"].append(base)
            write_import_log(activity_path, "上传Excel", source_path, report)
            return report
        target.unlink()
        old_blacklist = activity_path / f"{base}{BLACKLIST_SUFFIX}"
        if old_blacklist.exists():
            old_blacklist.unlink()
    try:
        copy_file(excel_path, target)
        report["imported"].append(base)
        ok, errors, warnings = validate_counselor_pair(activity_path, base)
        report["warnings"].extend(warnings)
        if not ok:
            report["errors"].extend(errors)
    finally:
        temp_dir = activity_path / ".upload_tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    write_import_log(activity_path, "上传Excel", source_path, report)
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
    clear_student_cache()
    root = resources_root()
    ensure_dir(root)
    report = {"imported": [], "skipped": [], "warnings": [], "errors": []}
    with zipfile.ZipFile(zip_path) as zf:
        members = [
            (info, normalize_zip_member_name(decode_zip_member_name(info)))
            for info in zf.infolist()
        ]
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
            if len(rel_parts) >= 2 and rel_parts[0] not in ROOT_RESOURCE_FILES:
                rel_parts = (DEFAULT_ACTIVITY_NAME, *rel_parts[1:])
            elif rel_parts == (CURRENT_ACTIVITY_FILE,):
                write_json(
                    root / CURRENT_ACTIVITY_FILE, {"activity": DEFAULT_ACTIVITY_NAME}
                )
                report["imported"].append(CURRENT_ACTIVITY_FILE)
                continue
            target = root.joinpath(*rel_parts)
            if target.exists() and not overwrite:
                report["skipped"].append(str(target.relative_to(root)))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            report["imported"].append(str(target.relative_to(root)))
    write_import_log(root, "导入历史数据", zip_path, report)
    return report


def download_template(destination: Optional[Path] = None) -> Path:
    source = app_root() / "template.zip"
    fallback = bundled_root() / "resources" / "template.zip"
    actual_source = (
        source if source.exists() else fallback if fallback.exists() else None
    )
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
        settings["enabled_rounds"] = (
            enabled or DEFAULT_CONTEST_SETTINGS["enabled_rounds"]
        )
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


def save_score(
    activity_path: Path, counselor_id: str, scores: dict[str, float]
) -> None:
    data = load_scores(activity_path)
    data[counselor_id] = scores
    write_json(scores_path(activity_path), data)


def export_scores(activity_path: Path, awards: Optional[dict[str, int]] = None) -> Path:
    data = load_scores(activity_path)
    rows = []
    ranked = sorted(
        data.items(), key=lambda item: float(item[1].get("总分", 0)), reverse=True
    )
    award_labels: dict[str, str] = {}
    if awards:
        cursor = 0
        for label in ("一等奖", "二等奖", "三等奖"):
            count = int(awards.get(label, 0))
            for counselor_id, _ in ranked[cursor : cursor + count]:
                award_labels[counselor_id] = label
            cursor += count
    for rank, (counselor_id, scores) in enumerate(ranked, start=1):
        row = {
            "排名": rank,
            "辅导员": counselor_id,
            **scores,
            "奖项": award_labels.get(counselor_id, ""),
        }
        rows.append(row)
    output = resources_root() / f"{activity_path.name}_成绩汇总.xlsx"
    pd.DataFrame(rows).to_excel(output, index=False)
    return output
