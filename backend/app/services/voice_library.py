from __future__ import annotations

import hashlib
import json
import importlib.util
import logging
import re
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.services import voice_store


PREVIEW_TEXT = "Xin chào, rất vui được gặp bạn hôm nay. Chúc bạn một ngày thật nhiều niềm vui và công việc luôn thuận lợi."
CLONE_ID = re.compile(r"clone_[a-f0-9]{32}")
logger = logging.getLogger(__name__)


def preview_path(voice: str) -> Path:
    # A listening sample is shared across CPU/CUDA and survives service restarts.
    key = hashlib.sha256(f"v2:{voice}:{PREVIEW_TEXT}".encode()).hexdigest()
    return library_dir() / "previews" / f"{key}.wav"


def preview_url(voice: str) -> str | None:
    path = preview_path(voice)
    return f"/api/system/tts/previews/{path.name}" if voice_store.has_preview(voice, path.stem) or path.is_file() else None


def _public_voice(row: dict) -> dict:
    item = {"id": row["id"], "label": row["label"]}
    if row["custom"]:
        item["custom"] = True
    key = row.get("preview_key")
    if row.get("has_preview") and key == preview_path(row["id"]).stem:
        item["preview_url"] = f"/api/system/tts/previews/{key}.wav"
    return item


def sync_library() -> None:
    """Import legacy files once. Never load the model or synthesize audio."""
    known = {row["id"]: row for row in voice_store.catalog()}
    entries = []
    voices_file = settings.vieneu_repo / "src" / "vieneu" / "assets" / "voices_v3_turbo.json" if hasattr(settings, "vieneu_repo") else None
    if voices_file is None or not voices_file.exists():
        package = importlib.util.find_spec("vieneu")
        voices_file = Path(package.origin).parent / "assets" / "voices_v3_turbo.json" if package and package.origin else None
    if voices_file and voices_file.exists():
        presets = json.loads(voices_file.read_text(encoding="utf-8")).get("presets", {})
        for voice_id, info in sorted(presets.items(), key=lambda pair: (pair[1].get("featured", 9999), pair[0])):
            if voice_id not in known:
                entries.append({"id": voice_id, "label": f"{'⭐ ' if info.get('featured') else ''}{voice_id} — {info.get('description', '')}",
                                "custom": False, "payload": {"voice": {"speaker_emb": info["speaker_emb"], "codes": info.get("codes")}}})
    for manifest in sorted(library_dir().glob("clone_*.json")):
        if not CLONE_ID.fullmatch(manifest.stem) or manifest.stem in known:
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        reference = manifest.with_suffix(".wav")
        entries.append({"id": manifest.stem, "label": f"Giọng clone · {payload['name']}", "custom": True,
                        "payload": payload, "reference_audio": reference.read_bytes() if reference.is_file() else None})
    voice_store.seed(entries)
    rows = voice_store.catalog() if entries else list(known.values())
    samples = []
    for row in rows:
        path = preview_path(row["id"])
        if row["preview_key"] == path.stem and row["has_preview"]:
            continue
        if path.is_file():
            samples.append((row["id"], path.stem, path.read_bytes()))
    if samples:
        voice_store.save_previews(samples)
    logger.info("Voice library ready: %s voices; imported %s definitions and %s existing samples", len(rows), len(entries), len(samples))


def saved_voices() -> list[dict]:
    rows = voice_store.catalog()
    if not rows:
        sync_library()
        rows = voice_store.catalog()
    return [_public_voice(row) for row in rows]


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
    return [{"id": row["id"], "label": row["label"], "custom": True} for row in voice_store.catalog(custom=True)]


def resolve_voice(voice: str):
    if voice.startswith("clone_") and not CLONE_ID.fullmatch(voice):
        raise ValueError("Giọng clone không hợp lệ")
    stored = voice_store.definition(voice)
    if stored is None and voice.startswith("clone_"):
        sync_library()
        stored = voice_store.definition(voice)
    if stored is None:
        if voice.startswith("clone_"):
            raise ValueError("Không tìm thấy giọng clone đã lưu")
        return voice
    import numpy as np

    data = stored["payload"].get("voice")
    if not data:
        return voice
    data["speaker_emb"] = np.asarray(data["speaker_emb"], dtype=np.float32)
    if data.get("codes") is not None:
        data["codes"] = np.asarray(data["codes"], dtype=np.int64)
        if not stored["custom"]:
            from vieneu_utils.core_utils import strip_encoder_pad_frame

            data["codes"] = strip_encoder_pad_frame(data["codes"])
    return data


def rename_voice(voice_id: str, name: str) -> dict:
    if not CLONE_ID.fullmatch(voice_id):
        raise ValueError("Chỉ đổi tên được giọng clone của bạn")
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Tên giọng phải có từ 1 đến 100 ký tự")
    if voice_store.definition(voice_id) is None:
        sync_library()
    voice_store.rename(voice_id, f"Giọng clone · {name}", name)
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
                voice_store.seed([{"id": voice_id, "label": f"Giọng clone · {name}", "custom": True,
                                   "payload": payload, "reference_audio": normalized.read_bytes()}])
            finally:
                engine.remove_voice(voice_id, save=False)
    return {"id": voice_id, "label": f"Giọng clone · {name}", "custom": True}


def preview_voice(voice: str, device: str) -> dict:
    from app.services.tts_service import tts_service

    if voice not in {item["id"] for item in tts_service.voices(device)}:
        raise ValueError("Không tìm thấy giọng đã chọn")
    destination = preview_path(voice)
    result = {"audio_url": f"/api/system/tts/previews/{destination.name}", "text": PREVIEW_TEXT}
    if voice_store.has_preview(voice, destination.stem):
        return result
    # Bring existing disk samples into the DB without synthesizing them again.
    voice_store.seed([{"id": voice, "label": voice, "custom": False, "payload": {}}])
    # Cached playback must not wait behind another voice being synthesized.
    if destination.is_file():
        voice_store.save_previews([(voice, destination.stem, destination.read_bytes())])
        return result
    with tts_service._lock:
        directory = destination.parent
        directory.mkdir(exist_ok=True)
        if not destination.exists():
            temporary = destination.with_suffix(".tmp.wav")
            try:
                tts_service.generate(PREVIEW_TEXT, voice, temporary, device, batch_size=1)
                voice_store.save_previews([(voice, destination.stem, temporary.read_bytes())])
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            voice_store.save_previews([(voice, destination.stem, destination.read_bytes())])
    return result
