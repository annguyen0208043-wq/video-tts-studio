from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


PREVIEW_TEXT = "Xin chào, rất vui được gặp bạn hôm nay. Chúc bạn một ngày thật nhiều niềm vui và công việc luôn thuận lợi."
CLONE_ID = re.compile(r"clone_[a-f0-9]{32}")
logger = logging.getLogger(__name__)


def preview_path(voice: str) -> Path:
    # A listening sample is shared across CPU/CUDA and survives service restarts.
    key = hashlib.sha256(f"v2:{voice}:{PREVIEW_TEXT}".encode()).hexdigest()
    return library_dir() / "previews" / f"{key}.wav"


def preview_url(voice: str) -> str | None:
    path = preview_path(voice)
    return f"/api/system/tts/previews/{path.name}" if path.is_file() else None


def prepare_previews(device: str) -> None:
    from app.services.tts_service import tts_service

    voices = tts_service.voices(device)
    for index, voice in enumerate(voices, start=1):
        try:
            preview_voice(voice["id"], device)
            logger.info("Voice preview ready %s/%s: %s", index, len(voices), voice["id"])
        except Exception:
            logger.exception("Could not prepare voice preview: %s", voice["id"])


def library_dir() -> Path:
    directory = settings.data_dir / "voices"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def custom_voices() -> list[dict]:
    result = []
    for path in sorted(library_dir().glob("clone_*.json")):
        if not CLONE_ID.fullmatch(path.stem):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result.append({"id": path.stem, "label": f"Giọng clone · {data['name']}", "custom": True})
    return result


def resolve_voice(voice: str):
    if not voice.startswith("clone_"):
        return voice
    if not CLONE_ID.fullmatch(voice):
        raise ValueError("Giọng clone không hợp lệ")
    path = library_dir() / f"{voice}.json"
    if not path.exists():
        raise ValueError("Không tìm thấy giọng clone đã lưu")
    import numpy as np

    data = json.loads(path.read_text(encoding="utf-8"))["voice"]
    data["speaker_emb"] = np.asarray(data["speaker_emb"], dtype=np.float32)
    if data.get("codes") is not None:
        data["codes"] = np.asarray(data["codes"], dtype=np.int64)
    return data


def rename_voice(voice_id: str, name: str) -> dict:
    from app.services.tts_service import tts_service

    if not CLONE_ID.fullmatch(voice_id):
        raise ValueError("Chỉ đổi tên được giọng clone của bạn")
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Tên giọng phải có từ 1 đến 100 ký tự")
    with tts_service._lock:
        path = library_dir() / f"{voice_id}.json"
        if not path.is_file():
            raise FileNotFoundError("Không tìm thấy giọng clone")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["name"] = name
        temporary = path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return {"id": voice_id, "label": f"Giọng clone · {name}", "custom": True, "preview_url": preview_url(voice_id)}


def clone_voice(name: str, source: Path, device: str) -> dict:
    from app.services.tts_service import tts_service
    import numpy as np
    import soundfile as sf

    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Tên giọng phải có từ 1 đến 100 ký tự")
    voice_id = f"clone_{uuid4().hex}"
    # Decode with a duration limit before the model sees untrusted audio.
    with tempfile.TemporaryDirectory(dir=library_dir()) as directory:
        normalized = Path(directory) / "reference.wav"
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(source), "-t", "31", "-vn", "-ac", "1", "-ar", "48000", str(normalized)],
            capture_output=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError("Không đọc được audio mẫu. Hãy dùng file WAV, MP3, M4A hoặc FLAC hợp lệ.")
        duration = sf.info(normalized).duration
        if not 3 <= duration <= 30:
            raise ValueError("Audio mẫu cần dài từ 3 đến 30 giây")
        with tts_service._lock:
            engine = tts_service._load(device)
            try:
                engine.add_voice(voice_id, normalized, description=name, save=False)
                preset = engine.get_preset_voice(voice_id)
                voice = {
                    "speaker_emb": np.asarray(preset["speaker_emb"], dtype=np.float32).tolist(),
                    "codes": np.asarray(preset["codes"], dtype=np.int64).tolist() if preset.get("codes") is not None else None,
                }
                payload = {"name": name, "voice": voice, "duration": duration}
                manifest = Path(directory) / "voice.json"
                manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                normalized.replace(library_dir() / f"{voice_id}.wav")
                manifest.replace(library_dir() / f"{voice_id}.json")
            finally:
                engine.remove_voice(voice_id, save=False)
    return {"id": voice_id, "label": f"Giọng clone · {name}", "custom": True}


def preview_voice(voice: str, device: str) -> dict:
    from app.services.tts_service import tts_service

    if voice not in {item["id"] for item in tts_service.voices(device)}:
        raise ValueError("Không tìm thấy giọng đã chọn")
    destination = preview_path(voice)
    result = {"audio_url": f"/api/system/tts/previews/{destination.name}", "text": PREVIEW_TEXT}
    # Cached playback must not wait behind another voice being synthesized.
    if destination.is_file():
        return result
    with tts_service._lock:
        directory = destination.parent
        directory.mkdir(exist_ok=True)
        if not destination.exists():
            temporary = destination.with_suffix(".tmp.wav")
            try:
                tts_service.generate(PREVIEW_TEXT, voice, temporary, device, batch_size=1)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
    return result
