from __future__ import annotations

import logging
import json
import os
import sys
import threading
from pathlib import Path

from app.core.config import settings


logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self) -> None:
        self._engine = None
        self._device = None
        self._lock = threading.Lock()

    def _load(self, device: str):
        normalized = device.lower()
        if normalized not in {"auto", "cuda", "cpu"}:
            raise ValueError("Device phải là auto, cuda hoặc cpu")
        backend = "onnx" if normalized == "cpu" else None
        with self._lock:
            if self._engine is not None and self._device == normalized:
                return self._engine
            src = settings.vieneu_repo / "src"
            if not src.exists():
                raise RuntimeError(f"Không tìm thấy VieNeu-TTS tại {settings.vieneu_repo}")
            if str(src) not in sys.path:
                sys.path.insert(0, str(src))
            # Models are already downloaded by the VieNeu installation. Avoid slow
            # network HEAD retries on every local application start.
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            try:
                from vieneu import Vieneu
            except Exception as exc:
                raise RuntimeError(f"Không import được VieNeu: {exc}") from exc
            kwargs = {}
            if backend:
                kwargs["backend"] = backend
            logger.info("Loading VieNeu engine device=%s", normalized)
            self._engine = Vieneu(**kwargs)
            self._device = normalized
            return self._engine

    def voices(self, device: str = "auto") -> list[dict[str, str]]:
        voices_file = settings.vieneu_repo / "src" / "vieneu" / "assets" / "voices_v3_turbo.json"
        if voices_file.exists():
            data = json.loads(voices_file.read_text(encoding="utf-8"))
            presets = data.get("presets", {})
            ordered = sorted(
                presets.items(),
                key=lambda item: (item[1].get("featured", 9999), item[0]),
            )
            return [
                {
                    "id": voice_id,
                    "label": f"{'⭐ ' if info.get('featured') else ''}{voice_id} — {info.get('description', '')}",
                }
                for voice_id, info in ordered
            ]
        engine = self._load(device)
        return [{"label": label, "id": voice_id} for label, voice_id in engine.list_preset_voices()]

    def generate(
        self,
        text: str,
        voice: str,
        destination: Path,
        device: str = "auto",
        **generation_options,
    ) -> None:
        engine = self._load(device)
        audio = engine.infer(text, voice=voice, **generation_options)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() == ".wav":
            engine.save(audio, str(destination))
            return
        temporary_wav = destination.with_suffix(".source.wav")
        engine.save(audio, str(temporary_wav))
        try:
            import subprocess

            codec_args = ["-c:a", "libmp3lame", "-b:a", "192k"] if destination.suffix.lower() == ".mp3" else []
            result = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(temporary_wav), *codec_args, str(destination)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "Không chuyển đổi được audio")
        finally:
            temporary_wav.unlink(missing_ok=True)

    @property
    def loaded(self) -> bool:
        return self._engine is not None


tts_service = TTSService()
