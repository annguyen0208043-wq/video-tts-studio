from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4


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
    temporary = destination.with_name(f".{destination.stem}.{uuid4().hex}.jpg")
    diagnostics = ""
    try:
        # Pick a representative frame, avoiding an empty opening frame. Very
        # short videos may end before 0.2 s, so retry from the beginning.
        for offset in ("0.2", "0"):
            proc = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", offset,
                 "-i", str(source), "-an", "-frames:v", "1", "-vf",
                 "thumbnail=30,scale=360:640:force_original_aspect_ratio=decrease,setsar=1",
                 "-q:v", "3", str(temporary)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0 and temporary.is_file() and temporary.stat().st_size:
                temporary.replace(destination)
                return
            diagnostics = proc.stderr.strip()
        raise ValueError(diagnostics or "Không tạo được thumbnail")
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Tạo ảnh đại diện video quá thời gian chờ") from exc
    finally:
        temporary.unlink(missing_ok=True)

