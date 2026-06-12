from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any


APP_NAME = "CogniStudent"


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return app_root() / "src"


def resources_root() -> Path:
    return app_root() / "resources"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_activity_name(name: str) -> str:
    invalid = '<>:"/\\|?*'
    cleaned = "".join(ch for ch in name.strip() if ch not in invalid)
    return cleaned.strip(". ")


def copy_file(src: Path, dst: Path) -> None:
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)

