from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path

from app.core.config import settings


PROJECT_SUBDIRS = (
    "source/videos",
    "source/audio",
    "generated/tts",
    "work/normalized",
    "work/concat",
    "outputs",
    "logs",
    "thumbnails",
)


def ensure_storage() -> None:
    settings.projects_dir.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    bgm_library_dir().mkdir(parents=True, exist_ok=True)


def bgm_library_dir() -> Path:
    """Return the global BGM library directory (not per-project)."""
    return (settings.data_dir / "bgm_library").resolve()


def project_dir(project_id: str) -> Path:
    root = (settings.projects_dir / project_id).resolve()
    if root.parent != settings.projects_dir.resolve():
        raise ValueError("Invalid project id")
    return root


def create_project_dirs(project_id: str) -> Path:
    root = project_dir(project_id)
    for item in PROJECT_SUBDIRS:
        (root / item).mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(name: str, fallback: str = "file") -> str:
    original = Path(name)
    suffix = original.suffix.lower()
    raw_stem = original.stem if suffix else name
    raw_stem = raw_stem.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", raw_stem)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_name).strip("-_.")
    return ((stem[:150] or fallback) + suffix)[:160]


def unique_destination(directory: Path, original_name: str) -> Path:
    cleaned = safe_filename(Path(original_name).name)
    stem, suffix = Path(cleaned).stem, Path(cleaned).suffix.lower()
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def relative_to_project(project_id: str, path: Path) -> str:
    return path.resolve().relative_to(project_dir(project_id)).as_posix()


def resolve_asset_path(project_id: str, relative_path: str) -> Path:
    root = project_dir(project_id)
    target = (root / relative_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Asset path is outside the project")
    return target


def delete_project_files(project_id: str) -> None:
    root = project_dir(project_id)
    if root.exists() and root.parent == settings.projects_dir.resolve():
        shutil.rmtree(root)
