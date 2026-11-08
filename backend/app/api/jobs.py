from __future__ import annotations

import asyncio
import json
import re
from contextlib import closing
from io import BytesIO
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from openpyxl import load_workbook
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models import Asset, BgmTrack, Job, Project, Sequence
from app.schemas.api import AudioBatchProcessCreate, AudioProcessJobCreate, JobOut, RenderItemCreate, RenderJobCreate, TTSJobCreate
from app.services.job_service import job_manager
from app.services.storage_service import safe_filename


router = APIRouter(tags=["jobs"])

BANGKOK_TIMEZONE = timezone(timedelta(hours=7))


def _next_render_group(db: Session, project_id: str, now: datetime) -> str:
    """Return day-index (for example 15-2), persisted independently per project."""
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    day_prefix = str(now.day)
    pattern = re.compile(rf"^{re.escape(day_prefix)}-(\d+)$")
    job_groups = db.scalars(
        select(Job.input_json["group_name"].as_string()).where(Job.project_id == project_id, Job.kind == "render")
    ).all()
    indexes: list[int] = []
    for group in job_groups:
        match = pattern.fullmatch(str(group or ""))
        if match:
            indexes.append(int(match.group(1)))
    return f"{day_prefix}-{max(indexes, default=0) + 1}"


def _next_tts_name(db: Session, project_id: str, requested_name: str) -> str:
    """Append a persistent, project-wide sequence number to a user supplied prefix."""
    # Serialise name allocation on PostgreSQL when several clicks arrive
    # together; keep the lock only until the new queued jobs are committed.
    db.execute(select(Project.id).where(Project.id == project_id).with_for_update())
    prefix = safe_filename(requested_name, "voice")
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    names = db.scalars(select(Job.input_json["name"].as_string()).where(Job.project_id == project_id, Job.kind == "tts")).all()
    used = []
    for name in names:
        match = pattern.match(str(name or ""))
        if match:
            used.append(int(match.group(1)))
    return f"{prefix}_{max(used, default=0) + 1}"


def _submit_jobs(jobs: list[tuple[str, str]]) -> None:
    for job_id, kind in jobs:
        job_manager.submit(job_id, kind=kind)


def _queue_tts_jobs(db: Session, project_id: str, payloads: list[dict], background_tasks: BackgroundTasks) -> list[Job]:
    jobs = [Job(project_id=project_id, kind="tts", status="queued", input_json=item) for item in payloads]
    db.add_all(jobs)
    db.commit()
    background_tasks.add_task(_submit_jobs, [(job.id, job.kind) for job in jobs])
    return jobs


@router.post("/projects/{project_id}/tts/jobs", response_model=JobOut, status_code=202)
def create_tts_job(project_id: str, payload: TTSJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project was not found")
    values = payload.model_dump()
    values["name"] = _next_tts_name(db, project_id, payload.name)
    return _queue_tts_jobs(db, project_id, [values], background_tasks)[0]


@router.post("/projects/{project_id}/tts/excel-jobs", response_model=list[JobOut], status_code=202)
def create_tts_excel_jobs(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: str = Form(...),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project was not found")
    if not (upload.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(415, "Chỉ hỗ trợ file Excel .xlsx")
    try:
        base_payload = TTSJobCreate.model_validate_json(settings)
    except Exception as exc:
        raise HTTPException(422, f"Tham số tạo giọng không hợp lệ: {exc}") from exc
    group_name = (base_payload.group_name or "").strip()
    if not group_name:
        raise HTTPException(422, "Hãy đặt tên nhóm audio trước khi nhập Excel")
    existing_groups = db.scalars(select(Job.input_json["group_name"].as_string()).where(Job.project_id == project_id, Job.kind == "tts")).all()
    existing_groups += db.scalars(select(Asset.metadata_json["group_name"].as_string()).where(Asset.project_id == project_id)).all()
    if group_name.casefold() in {str(name).strip().casefold() for name in existing_groups if name}:
        raise HTTPException(409, "Tên nhóm đã được sử dụng. Hãy chọn tên nhóm mới.")
    base_payload.group_name = group_name
    # Excel parsing and the synchronous DB session belong in FastAPI's worker
    # pool, otherwise a large workbook stalls every request and event stream.
    content = upload.file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File Excel không được vượt quá 10 MB")
    try:
        with closing(load_workbook(BytesIO(content), read_only=True, data_only=True)) as workbook:
            sheet = workbook.active
            # Bound rows and columns while reading, rather than loading an
            # entire worksheet before enforcing the 1000-entry limit.
            rows = []
            for row in sheet.iter_rows(values_only=True, max_col=2):
                rows.append(row)
                if len(rows) > 1001:
                    raise HTTPException(400, "Mỗi lần chỉ được nhập tối đa 1000 đoạn")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Không thể đọc file Excel") from exc
    if not rows or len(rows[0]) < 2:
        raise HTTPException(400, "Excel phải có 2 cột STT và text")
    header = [str(value or "").strip().lower() for value in rows[0][:2]]
    if header != ["stt", "text"]:
        raise HTTPException(400, "Dòng đầu tiên phải có đúng 2 tiêu đề: STT và text")
    parsed: list[tuple[int, str]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        stt, text = (list(row) + [None, None])[:2]
        if stt is None and (text is None or not str(text).strip()):
            continue
        try:
            numeric_stt = float(stt)
            number = int(numeric_stt)
            if numeric_stt != number:
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(400, f"STT không hợp lệ tại dòng {row_number}")
        value = str(text or "").strip()
        if not value:
            raise HTTPException(400, f"Thiếu text tại dòng {row_number}")
        parsed.append((number, value))
    if not parsed:
        raise HTTPException(400, "File Excel không có nội dung để tạo giọng")
    if len(parsed) > 1000:
        raise HTTPException(400, "Mỗi lần chỉ được nhập tối đa 1000 đoạn")
    expected = list(range(1, len(parsed) + 1))
    if [number for number, _ in parsed] != expected:
        raise HTTPException(400, "Cột STT phải liên tục từ 1 đến n, không trùng hoặc bỏ số")
    prefix = safe_filename(base_payload.name, "voice")
    first_name = _next_tts_name(db, project_id, prefix)
    first_index = int(first_name.rsplit("_", 1)[1])
    payloads = []
    for offset, (number, value) in enumerate(parsed):
        item = base_payload.model_dump()
        item.update(text=value, name=f"{prefix}_{first_index + offset}", source_stt=number)
        payloads.append(item)
    return _queue_tts_jobs(db, project_id, payloads, background_tasks)


@router.post("/assets/{asset_id}/audio/jobs", response_model=JobOut, status_code=202)
def create_audio_process_job(
    asset_id: str, payload: AudioProcessJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    asset = db.get(Asset, asset_id)
    if not asset or asset.type not in {"tts_audio", "external_audio"}:
        raise HTTPException(404, "Audio asset was not found")
    if payload.trim_end is not None and payload.trim_end <= payload.trim_start:
        raise HTTPException(400, "Trim end must be greater than trim start")
    if asset.duration_ms and payload.trim_start >= asset.duration_ms / 1000:
        raise HTTPException(400, "Trim start is outside the audio duration")
    job = Job(
        project_id=asset.project_id,
        kind="audio_process",
        status="queued",
        input_json={"asset_id": asset.id, **payload.model_dump()},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_submit_jobs, [(job.id, job.kind)])
    return job


@router.post("/projects/{project_id}/audio/batch-jobs", response_model=list[JobOut], status_code=202)
def create_audio_batch_jobs(
    project_id: str, payload: AudioBatchProcessCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    assets = db.scalars(
        select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.project_id == project_id)
    ).all()
    if len(assets) != len(set(payload.asset_ids)) or any(
        asset.type not in {"tts_audio", "external_audio"} for asset in assets
    ):
        raise HTTPException(400, "Một hoặc nhiều audio không hợp lệ")
    asset_map = {asset.id: asset for asset in assets}
    jobs: list[Job] = []
    speed_label = str(payload.speed).replace(".", "-")
    for asset_id in payload.asset_ids:
        asset = asset_map[asset_id]
        job = Job(
            project_id=project_id,
            kind="audio_process",
            status="queued",
            input_json={
                "asset_id": asset.id,
                "name": f"{asset.display_name}-{speed_label}x",
                "speed": payload.speed,
                "trim_start": 0,
                "trim_end": None,
                "output_format": payload.output_format,
                "group_name": asset.metadata_json.get("group_name"),
            },
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    background_tasks.add_task(_submit_jobs, [(job.id, job.kind) for job in jobs])
    return jobs


@router.post("/projects/{project_id}/render/jobs", response_model=list[JobOut], status_code=202)
def create_render_jobs(project_id: str, payload: RenderJobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project was not found")
    render_items = payload.items or [
        RenderItemCreate(
            sequence_id=sequence_id,
            audio_asset_id=payload.audio_asset_id,
            source_audio_policy=payload.source_audio_policy,
        )
        for sequence_id in payload.sequence_ids
    ]
    if not render_items:
        raise HTTPException(400, "At least one render item is required")
    if not payload.allow_missing_audio and any(not item.audio_asset_id for item in render_items):
        raise HTTPException(400, "Cần gán đủ audio hoặc bật cho phép xuất video thiếu audio")
    voice_ids = [item.audio_asset_id for item in render_items if item.audio_asset_id]
    if not payload.allow_duplicate_audio and len(voice_ids) != len(set(voice_ids)):
        raise HTTPException(400, "Audio bị trùng. Cần cho phép dùng trùng trước khi render.")
    sequence_ids = [item.sequence_id for item in render_items]
    sequences = db.scalars(
        select(Sequence).where(Sequence.id.in_(sequence_ids), Sequence.project_id == project_id)
    ).all()
    if len(sequences) != len(set(sequence_ids)):
        raise HTTPException(400, "One or more sequences are invalid")
    voice_asset_ids = {item.audio_asset_id for item in render_items if item.audio_asset_id}
    if voice_asset_ids:
        voice_assets = db.scalars(
            select(Asset).where(Asset.id.in_(voice_asset_ids), Asset.project_id == project_id)
        ).all()
        if len(voice_assets) != len(voice_asset_ids) or any(
            audio.type not in {"tts_audio", "external_audio"} for audio in voice_assets
        ):
            raise HTTPException(400, "One or more voice audio assets are invalid")

    bgm_asset_ids = {item.bgm_asset_id for item in render_items if item.bgm_asset_id}
    if bgm_asset_ids:
        project_bgm_assets = db.scalars(
            select(Asset).where(Asset.id.in_(bgm_asset_ids), Asset.project_id == project_id)
        ).all()
        global_bgm_tracks = db.scalars(
            select(BgmTrack).where(BgmTrack.id.in_(bgm_asset_ids))
        ).all()
        valid_bgm_ids = {
            audio.id
            for audio in project_bgm_assets
            if audio.type in {"tts_audio", "external_audio"}
        } | {track.id for track in global_bgm_tracks}
        if valid_bgm_ids != bgm_asset_ids:
            raise HTTPException(400, "One or more background music tracks are invalid")

    values = payload.model_dump()
    option_keys = {
        "duration_policy",
        "source_audio_policy",
        "resolution",
        "fps",
        "video_encoder",
        "fit_mode",
        "voice_volume",
        "source_volume",
        "bgm_volume",
    }
    base_options = {key: values[key] for key in option_keys}
    now = datetime.now(BANGKOK_TIMEZONE)
    group_name = _next_render_group(db, project_id, now)
    output_root = safe_filename(payload.output_folder, "renders")
    # One click creates one named output group, even when source batches differ.
    run_folder = f"{output_root}/{group_name}"
    sequence_map = {sequence.id: sequence for sequence in sequences}
    jobs: list[Job] = []
    for output_index, item in enumerate(render_items, start=1):
        sequence = sequence_map[item.sequence_id]
        batch_name = sequence.batch_name or "Batch"
        options = dict(base_options)
        options["source_audio_policy"] = item.source_audio_policy
        options["voice_volume"] = item.voice_volume
        options["bgm_volume"] = item.bgm_volume
        job = Job(
            project_id=project_id,
            kind="render",
            status="queued",
            input_json={
                "sequence_id": item.sequence_id,
                "audio_asset_id": item.audio_asset_id,
                "bgm_asset_id": item.bgm_asset_id,
                "custom_name": group_name,
                "output_filename": f"{group_name}-v{output_index}.mp4",
                "output_index": output_index,
                "batch_name": batch_name,
                "group_name": group_name,
                "run_timestamp": group_name,
                "run_folder": run_folder,
                "options": options,
            },
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    background_tasks.add_task(_submit_jobs, [(job.id, job.kind) for job in jobs])
    return jobs


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    statement = select(Job)
    if project_id:
        statement = statement.where(Job.project_id == project_id)
    recent = statement.order_by(Job.created_at.desc()).limit(limit).with_only_columns(Job.id)
    # Keep older queued/running jobs visible even after a 1000-row Excel import.
    return db.scalars(statement.where(or_(
        Job.id.in_(recent), Job.status.in_({"queued", "running", "rendering", "processing"})
    )).order_by(Job.created_at.desc())).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job was not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job was not found")
    if job.status in {"completed", "failed", "cancelled"}:
        return job
    job_manager.cancel(job_id)
    job.status = "cancelled"
    job.error_message = "Cancelled by the user"
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    original = db.get(Job, job_id)
    if not original:
        raise HTTPException(404, "Job was not found")
    if original.status not in {"failed", "cancelled"}:
        raise HTTPException(400, "Only failed or cancelled jobs can be retried")
    retry = Job(
        project_id=original.project_id,
        kind=original.kind,
        status="queued",
        input_json=original.input_json,
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    background_tasks.add_task(_submit_jobs, [(retry.id, retry.kind)])
    return retry


@router.get("/events")
async def events(project_id: str):
    def snapshot() -> str:
        with SessionLocal() as db:
            # Recently changed jobs must stay in the stream after completion,
            # even when 1000 newer queued jobs were imported in one batch.
            recent = select(Job.id).where(Job.project_id == project_id).order_by(Job.updated_at.desc(), Job.created_at.desc()).limit(100)
            rows = db.execute(select(
                Job.id, Job.status, Job.progress, Job.error_message, Job.output_asset_id,
            ).where(Job.project_id == project_id, or_(
                Job.id.in_(recent), Job.status.in_({"queued", "running", "rendering", "processing"})
            )).order_by(Job.created_at.desc())).mappings().all()
            return json.dumps([dict(row) for row in rows], ensure_ascii=False)

    async def stream():
        previous = ""
        while True:
            payload = await run_in_threadpool(snapshot)
            if payload != previous:
                yield f"event: jobs\ndata: {payload}\n\n"
                previous = payload
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(stream(), media_type="text/event-stream")
