from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: dict | None = None


class ProjectOut(ORMModel):
    id: str
    name: str
    settings: dict
    created_at: datetime
    updated_at: datetime


class AssetOut(ORMModel):
    id: str
    project_id: str
    type: str
    display_name: str
    relative_path: str
    thumbnail_path: str | None
    duration_ms: int | None
    width: int | None
    height: int | None
    fps: float | None
    codec: str | None
    has_audio: bool
    metadata_json: dict
    video_batch_name: str | None
    created_at: datetime


class VideoBatchAssignment(BaseModel):
    batch_name: str | None = Field(default=None, max_length=200)


class OutputBatchRename(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=1000)
    base_name: str = Field(min_length=1, max_length=150)


class OutputBatchDownload(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=1000)


class SequenceGenerate(BaseModel):
    video_asset_ids: list[str] = Field(min_length=1)
    mode: str
    length: int | None = Field(default=None, ge=1, le=20)
    limit: int = Field(default=100, ge=1, le=1000)
    replace_existing: bool = False
    batch_name: str = Field(default="Batch 1", min_length=1, max_length=200)


class SequenceManual(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    video_asset_ids: list[str] = Field(min_length=1)
    batch_name: str = Field(default="Batch 1", min_length=1, max_length=200)


class SequenceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


class SequenceItemOut(ORMModel):
    id: str
    asset_id: str
    position: int
    asset: AssetOut


class SequenceOut(ORMModel):
    id: str
    project_id: str
    name: str
    batch_name: str
    enabled: bool
    items: list[SequenceItemOut]
    created_at: datetime


class TTSJobCreate(BaseModel):
    text: str = Field(min_length=1, max_length=100_000)
    voice: str
    device: str = "auto"
    name: str = "voice"
    group_name: str | None = Field(default=None, max_length=100)
    output_format: str = "mp3"
    use_batch: bool = True
    batch_size: int = Field(default=16, ge=1, le=64)
    temperature: float = Field(default=0.8, ge=0.1, le=1.5)
    max_chars: int = Field(default=256, ge=128, le=512)
    top_k: int = Field(default=25, ge=0, le=200)
    top_p: float = Field(default=0.95, ge=0.1, le=1.0)
    repetition_penalty: float = Field(default=1.2, ge=1.0, le=2.0)
    silence_p: float = Field(default=0.15, ge=0, le=3.0)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class AudioProcessJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    trim_start: float = Field(default=0, ge=0)
    trim_end: float | None = Field(default=None, gt=0)
    output_format: str = "mp3"


class AudioBatchProcessCreate(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=200)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    output_format: str = "mp3"


class RenderItemCreate(BaseModel):
    sequence_id: str
    audio_asset_id: str | None = None
    bgm_asset_id: str | None = None
    source_audio_policy: str = "mute"
    voice_volume: float = Field(default=1.0, ge=0, le=4.0)
    bgm_volume: float = Field(default=1.0, ge=0, le=4.0)
    custom_name: str | None = Field(default=None, max_length=100)


class RenderJobCreate(BaseModel):
    allow_missing_audio: bool = False
    allow_duplicate_audio: bool = False
    sequence_ids: list[str] = Field(default_factory=list)
    items: list[RenderItemCreate] = Field(default_factory=list)
    audio_asset_id: str | None = None
    bgm_asset_id: str | None = None
    duration_policy: str = "match_audio_loop_video"
    source_audio_policy: str = "mute"
    resolution: str = "1920x1080"
    fps: int = Field(default=30, ge=1, le=120)
    video_encoder: str = "h264_nvenc"
    fit_mode: str = "fit"
    voice_volume: float = Field(default=1.0, ge=0, le=4)
    source_volume: float = Field(default=0.25, ge=0, le=4)
    bgm_volume: float = Field(default=1.0, ge=0, le=4)
    run_name: str = Field(default="output", min_length=1, max_length=100)
    group_name: str = Field(default="Nhóm render", min_length=1, max_length=100)
    output_folder: str = Field(default="renders", min_length=1, max_length=100)


class JobOut(ORMModel):
    id: str
    project_id: str
    kind: str
    status: str
    progress: float
    input_json: dict
    output_asset_id: str | None
    error_message: str | None
    log_path: str | None
    created_at: datetime
    updated_at: datetime


class ScriptGenerate(BaseModel):
    product_info: str = Field(min_length=3, max_length=20_000)
    skill_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    provider: str = "auto"
    count: int = Field(default=5, ge=1, le=100)
    duration_min: int = Field(default=18, ge=5, le=120)
    duration_max: int = Field(default=20, ge=5, le=120)


class GeneratedScript(BaseModel):
    index: int
    text: str
    estimated_duration_seconds: float
    warnings: list[str] = Field(default_factory=list)


class ScriptGenerateOut(BaseModel):
    provider_used: str
    model_used: str
    scripts: list[GeneratedScript]


class BgmTrackOut(ORMModel):
    id: str
    display_name: str
    relative_path: str
    duration_ms: int | None
    codec: str | None
    tags: str | None
    file_size: int | None
    created_at: datetime


class BgmTrackUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    tags: str | None = None

