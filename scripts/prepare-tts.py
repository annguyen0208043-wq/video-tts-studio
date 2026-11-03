"""Download and smoke-test TTS: prepare-tts.py [cpu|cuda]."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(root / ".tools" / "huggingface")
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.path.insert(0, str(root / "backend"))
from app.services.tts_service import tts_service

device = sys.argv[1] if len(sys.argv) > 1 else "cpu"
voices = tts_service.voices(device)
print(f"Preset voices: {len(voices)}", flush=True)
output = root / ".tools" / f"tts-check-{device}.wav"
tts_service.generate("Xin chào, hệ thống đã sẵn sàng.", voices[0]["id"], output, device=device)
if device == "cuda":
    engine = tts_service._engine.engine
    assert engine.device.type == "cuda"
    print(f"Model device: {next(engine.model.parameters()).device}", flush=True)
assert output.exists() and output.stat().st_size > 44
print(f"TTS OK: {output}", flush=True)
