from __future__ import annotations

import logging
import importlib.util
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
        self._lock = threading.RLock()
        self._preload_thread: threading.Thread | None = None

    def _load(self, device: str):
        normalized = device.lower()
        if normalized not in {"auto", "cuda", "cpu"}:
            raise ValueError("Device phải là auto, cuda hoặc cpu")
        backend = "onnx" if normalized == "cpu" else None
        with self._lock:
            # `auto` and `cuda` both use the PyTorch backend. Treat them as the
            # same loaded engine so a UI request for CUDA does not reload a
            # model that startup already preloaded with `TTS_DEVICE=auto`.
            same_backend = (self._device == "cpu") == (normalized == "cpu")
            if self._engine is not None and same_backend:
                return self._engine
            src = settings.vieneu_repo / "src"
            if not src.exists() and importlib.util.find_spec("vieneu") is None:
                raise RuntimeError(f"Không tìm thấy VieNeu-TTS tại {settings.vieneu_repo}")
            if src.exists() and str(src) not in sys.path:
                sys.path.insert(0, str(src))
            # Models are already downloaded by the VieNeu installation. Avoid slow
            # network HEAD retries on every local application start.
            offline = os.getenv("VIENEU_OFFLINE", "1")
            os.environ.setdefault("HF_HUB_OFFLINE", offline)
            os.environ.setdefault("TRANSFORMERS_OFFLINE", offline)
            try:
                from vieneu import Vieneu
            except Exception as exc:
                raise RuntimeError(f"Không import được VieNeu: {exc}") from exc
            kwargs = {"device": normalized}
            if backend:
                kwargs["backend"] = backend
            elif normalized in {"auto", "cuda"}:
                import torch

                if torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] < 8:
                    # Older NVIDIA cards such as GTX 1070 do not support BF16.
                    kwargs["dtype"] = "float32"
            logger.info("Loading VieNeu engine device=%s", normalized)
            self._engine = Vieneu(**kwargs)
            self._device = normalized
            return self._engine

    def voices(self, device: str = "auto") -> list[dict[str, str]]:
        from app.services.voice_library import saved_voices

        return saved_voices()

    def generate(
        self, text: str, voice: str, destination: Path, device: str = "auto", **generation_options,
    ) -> None:
        # Jobs, clone encoding and previews all share the same model and GPU.
        with self._lock:
            self._generate_unlocked(text, voice, destination, device, **generation_options)

    def _generate_unlocked(
        self,
        text: str,
        voice: str,
        destination: Path,
        device: str = "auto",
        **generation_options,
    ) -> None:
        engine = self._load(device)
        from app.services.voice_library import resolve_voice

        audio = engine.infer(text, voice=resolve_voice(voice), **generation_options)
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

    def preload(self, device: str = "auto") -> None:
        """Load the model in the background so the first TTS job does not pay startup cost."""
        try:
            logger.info("Preloading VieNeu engine device=%s", device)
            self._load(device)
            logger.info("VieNeu engine preload completed")
        except Exception:
            # Keep the API available. A later TTS job will retry and expose the
            # concrete error through the normal job status.
            logger.exception("VieNeu engine preload failed")

    def preload_async(self, device: str = "auto") -> None:
        if self._preload_thread and self._preload_thread.is_alive():
            return
        self._preload_thread = threading.Thread(
            target=self.preload,
            args=(device,),
            name="tts-preload",
            daemon=True,
        )
        self._preload_thread.start()

    @property
    def loaded(self) -> bool:
        return self._engine is not None


tts_service = TTSService()
