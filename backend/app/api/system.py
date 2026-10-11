from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.services.media_probe import executable_status
from app.services.tts_service import tts_service


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
            [str(settings.vieneu_repo / ".venv" / "Scripts" / "python.exe"), "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
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
        return tts_service.voices(device)
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc

