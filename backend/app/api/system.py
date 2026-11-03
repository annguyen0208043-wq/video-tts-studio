from __future__ import annotations

import shutil
import subprocess
import sys
import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.services.media_probe import executable_status
from app.services.tts_service import tts_service
from app.services.voice_library import clone_voice, preview_voice, preview_url, library_dir, rename_voice


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
def system_status():
    media = executable_status()
    database = {"ok": False, "error": None}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database["ok"] = True
    except Exception as exc:
        database["error"] = str(exc)
    cuda = {"available": False, "device": None, "error": None}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = proc.stdout.strip().splitlines()
        cuda["available"] = bool(lines and lines[0] == "True")
        cuda["device"] = lines[1] if len(lines) > 1 else None
        if proc.returncode != 0:
            cuda["error"] = proc.stderr.strip()
    except Exception as exc:
        cuda["error"] = str(exc)
    usage = shutil.disk_usage(settings.data_dir.parent)
    return {
        "app": settings.app_name,
        "database": database,
        "media": media,
        "cuda": cuda,
        "tts_loaded": tts_service.loaded,
        "data_dir": str(settings.data_dir),
        "disk_free_bytes": usage.free,
    }


@router.get("/tts/voices")
def tts_voices(device: str = "auto"):
    try:
        return [{**voice, "preview_url": preview_url(voice["id"])} for voice in tts_service.voices(device)]
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc


class VoicePreview(BaseModel):
    voice: str = Field(min_length=1, max_length=200)
    device: Literal["auto", "cpu", "cuda"] = "auto"


class VoiceRename(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.patch("/tts/voices/{voice_id}")
def rename_cloned_voice(voice_id: str, payload: VoiceRename):
    try:
        return rename_voice(voice_id, payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/tts/voices/clone", status_code=201)
def create_cloned_voice(
    name: str = Form(..., min_length=1, max_length=100),
    device: Literal["auto", "cpu", "cuda"] = Form("auto"),
    upload: UploadFile = File(...),
):
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"}:
        raise HTTPException(415, "Hãy chọn audio WAV, MP3, M4A, FLAC, OGG hoặc WebM")
    try:
        with tempfile.TemporaryDirectory(dir=library_dir()) as directory:
            source = Path(directory) / f"upload{suffix}"
            size = 0
            with source.open("wb") as output:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 20 * 1024 * 1024:
                        raise HTTPException(413, "Audio mẫu không được vượt quá 20 MB")
                    output.write(chunk)
            if not size:
                raise HTTPException(400, "Audio mẫu đang trống")
            return clone_voice(name, source, device)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, f"Chưa clone được giọng: {exc}") from exc


@router.post("/tts/preview")
def create_voice_preview(payload: VoicePreview):
    try:
        return preview_voice(payload.voice, payload.device)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Chưa tạo được bản nghe thử: {exc}") from exc


@router.get("/tts/previews/{filename}")
def get_voice_preview(filename: str):
    if not re.fullmatch(r"[a-f0-9]{64}\.wav", filename):
        raise HTTPException(404, "Không tìm thấy bản nghe thử")
    path = library_dir() / "previews" / filename
    if not path.is_file():
        raise HTTPException(404, "Không tìm thấy bản nghe thử")
    return FileResponse(path, media_type="audio/wav")

