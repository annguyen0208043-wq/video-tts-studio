from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}


def executable_status() -> dict:
    result: dict[str, object] = {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "nvenc": False,
    }
    if result["ffmpeg"]:
        proc = subprocess.run(
            [str(result["ffmpeg"]), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        result["nvenc"] = "h264_nvenc" in proc.stdout
        version = subprocess.run(
            [str(result["ffmpeg"]), "-version"], capture_output=True, text=True, errors="replace"
        ).stdout.splitlines()
        result["version"] = version[0] if version else None
    return result


def _ratio(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        a, b = value.split("/", 1)
        return float(a) / float(b) if float(b) else None
    except (ValueError, ZeroDivisionError):
        return None


def probe(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise ValueError(f"FFprobe không đọc được file: {proc.stderr.strip()}")
    raw = json.loads(proc.stdout)
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = raw.get("format", {}).get("duration")
    if duration is None and video:
        duration = video.get("duration")
    return {
        "duration_ms": round(float(duration) * 1000) if duration else None,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "fps": _ratio(video.get("avg_frame_rate")) if video else None,
        "codec": (video or audio or {}).get("codec_name"),
        "has_audio": audio is not None,
        "raw": raw,
    }


def create_thumbnail(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "0.2",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=480:-2",
            str(destination),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr.strip() or "Không tạo được thumbnail")

