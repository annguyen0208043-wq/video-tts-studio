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
    skills_dir: Path = _resolve_path(os.getenv("SKILLS_DIR", "./skills"), "./skills")
    ai_default_provider: str = os.getenv("AI_DEFAULT_PROVIDER", "auto").lower()
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    ai_max_retries: int = int(os.getenv("AI_MAX_RETRIES", "1"))
    ai_cooldown_seconds: int = int(os.getenv("AI_COOLDOWN_SECONDS", "60"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "")

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


settings = Settings()
