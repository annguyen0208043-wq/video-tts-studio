from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def _resolve_path(value: str, default: str) -> Path:
    path = Path(value or default)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Video TTS Studio"
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8765"))
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://video_tts_app:change_me@127.0.0.1:5432/video_tts_studio",
    )
    data_dir: Path = _resolve_path(os.getenv("DATA_DIR", "./data"), "./data")
    log_dir: Path = _resolve_path(os.getenv("LOG_DIR", "./logs"), "./logs")
    vieneu_repo: Path = _resolve_path(os.getenv("VIENEU_REPO", "../VieNeu-TTS"), "../VieNeu-TTS")
    tts_device: str = os.getenv("TTS_DEVICE", "auto")
    max_sequence_outputs: int = int(os.getenv("MAX_SEQUENCE_OUTPUTS", "100"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "4096"))
    max_concurrent_jobs: int = int(os.getenv("MAX_CONCURRENT_JOBS", "3"))

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
