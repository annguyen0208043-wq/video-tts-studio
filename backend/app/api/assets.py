from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from starlette.background import BackgroundTask
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import Asset, Project
from app.schemas.api import AssetOut, OutputBatchDownload, OutputBatchRename, VideoBatchAssignment
from app.services.media_probe import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, create_thumbnail, probe
from app.services.storage_service import (
    create_project_dirs,
    relative_to_project,
    resolve_asset_path,
    safe_filename,
    unique_destination,
)


router = APIRouter(tags=["assets"])


@router.post("/projects/{project_id}/assets/import", response_model=list[AssetOut], status_code=201)
def import_assets(
    project_id: str,
    files: list[UploadFile] = File(...),
    batch_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    root = create_project_dirs(project_id)
    assigned_batch = batch_name.strip() if batch_name else None
    if batch_name is not None and not assigned_batch:
        raise HTTPException(400, "Tên batch không được để trống")
    created: list[Asset] = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            asset_type, folder = "video", root / "source" / "videos"
        elif suffix in AUDIO_EXTENSIONS:
            asset_type, folder = "external_audio", root / "source" / "audio"
        else:
            raise HTTPException(415, f"Định dạng không hỗ trợ: {suffix or upload.filename}")
        destination = unique_destination(folder, upload.filename or f"upload{suffix}")
        size = 0
        try:
            with destination.open("wb") as target:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_mb * 1024 * 1024:
                        raise HTTPException(413, f"File vượt {settings.max_upload_mb} MB")
                    target.write(chunk)
            info = probe(destination)
            thumbnail = None
            if asset_type == "video":
                thumbnail_file = root / "thumbnails" / f"{destination.stem}.jpg"
                try:
                    create_thumbnail(destination, thumbnail_file)
                    thumbnail = relative_to_project(project_id, thumbnail_file)
                except ValueError:
                    thumbnail = None
            asset = Asset(
                project_id=project_id,
                type=asset_type,
                display_name=Path(upload.filename or destination.name).stem,
                relative_path=relative_to_project(project_id, destination),
                thumbnail_path=thumbnail,
                duration_ms=info["duration_ms"],
                width=info["width"],
                height=info["height"],
                fps=info["fps"],
                codec=info["codec"],
                has_audio=info["has_audio"],
                metadata_json={"original_name": upload.filename, "size_bytes": size},
                video_batch_name=assigned_batch if asset_type == "video" else None,
            )
            db.add(asset)
            created.append(asset)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            upload.file.close()
    db.commit()
    for asset in created:
        db.refresh(asset)
    return created


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
def list_assets(
    project_id: str,
    asset_type: str | None = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
):
    statement = select(Asset).where(Asset.project_id == project_id)
    if asset_type:
        statement = statement.where(Asset.type == asset_type)
    return db.scalars(statement.order_by(Asset.created_at.desc())).all()


def _asset_or_404(asset_id: str, db: Session) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Không tìm thấy asset")
    return asset


@router.patch("/assets/{asset_id}/video-batch", response_model=AssetOut)
def assign_video_batch(
    asset_id: str,
    payload: VideoBatchAssignment,
    db: Session = Depends(get_db),
):
    asset = _asset_or_404(asset_id, db)
    if asset.type != "video":
        raise HTTPException(400, "Chỉ video nguồn mới có thể được gán vào batch")
    batch_name = payload.batch_name.strip() if payload.batch_name else None
    if payload.batch_name is not None and not batch_name:
        raise HTTPException(400, "Tên batch không được để trống")
    asset.video_batch_name = batch_name
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/assets/{asset_id}/stream")
def stream_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset_or_404(asset_id, db)
    path = resolve_asset_path(asset.project_id, asset.relative_path)
    if not path.exists():
        raise HTTPException(404, "File asset không còn tồn tại")
    # FileResponse may keep streaming for a long time (and browsers open many
    # parallel Range requests). The asset row is no longer needed, so return
    # the DB connection to the pool before sending file bytes.
    db.close()
    return FileResponse(path, filename=path.name)


@router.get("/assets/{asset_id}/thumbnail")
def asset_thumbnail(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset_or_404(asset_id, db)
    if not asset.thumbnail_path:
        raise HTTPException(404, "Asset không có thumbnail")
    path = resolve_asset_path(asset.project_id, asset.thumbnail_path)
    db.close()
    return FileResponse(path, media_type="image/jpeg")


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    asset = _asset_or_404(asset_id, db)
    paths = [resolve_asset_path(asset.project_id, asset.relative_path)]
    if asset.thumbnail_path:
        paths.append(resolve_asset_path(asset.project_id, asset.thumbnail_path))
    db.delete(asset)
    db.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.patch("/projects/{project_id}/outputs/rename", response_model=list[AssetOut])
def rename_output_batch(
    project_id: str, payload: OutputBatchRename, db: Session = Depends(get_db)
):
    assets = db.scalars(
        select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.project_id == project_id)
    ).all()
    if len(assets) != len(set(payload.asset_ids)) or any(asset.type != "output" for asset in assets):
        raise HTTPException(400, "Một hoặc nhiều video output không hợp lệ")
    asset_map = {asset.id: asset for asset in assets}
    ordered = [asset_map[asset_id] for asset_id in payload.asset_ids]
    base_name = safe_filename(Path(payload.base_name).stem, "video")
    targets: list[tuple[Asset, Path, Path]] = []
    source_paths = {resolve_asset_path(asset.project_id, asset.relative_path).resolve() for asset in ordered}
    for index, asset in enumerate(ordered, 1):
        source = resolve_asset_path(asset.project_id, asset.relative_path)
        if not source.exists():
            raise HTTPException(404, f"Không tìm thấy file {asset.display_name}")
        target = source.with_name(f"{base_name}-{index}{source.suffix.lower()}")
        if target.exists() and target.resolve() not in source_paths:
            raise HTTPException(409, f"Tên file đã tồn tại: {target.name}")
        targets.append((asset, source, target))

    staged: list[tuple[Asset, Path, Path, Path]] = []
    try:
        for asset, source, target in targets:
            temporary = source.with_name(f".{asset.id}.rename{source.suffix}")
            source.replace(temporary)
            staged.append((asset, temporary, target, source))
        for asset, temporary, target, _ in staged:
            temporary.replace(target)
            asset.display_name = target.name
            asset.relative_path = relative_to_project(project_id, target)
        db.commit()
    except Exception as exc:
        db.rollback()
        for _, temporary, target, source in reversed(staged):
            current = temporary if temporary.exists() else target
            if current.exists() and current != source:
                current.replace(source)
        if isinstance(exc, PermissionError):
            raise HTTPException(409, "File đang được trình phát hoặc chương trình khác sử dụng. Hãy dừng video rồi thử lại.") from exc
        raise
    for asset in ordered:
        db.refresh(asset)
    return ordered


@router.post("/projects/{project_id}/outputs/download")
def download_output_batch(
    project_id: str, payload: OutputBatchDownload, db: Session = Depends(get_db)
):
    assets = db.scalars(
        select(Asset).where(Asset.id.in_(payload.asset_ids), Asset.project_id == project_id)
    ).all()
    if len(assets) != len(set(payload.asset_ids)) or any(asset.type != "output" for asset in assets):
        raise HTTPException(400, "Một hoặc nhiều video output không hợp lệ")
    asset_map = {asset.id: asset for asset in assets}
    ordered = [asset_map[asset_id] for asset_id in payload.asset_ids]
    db.close()
    temporary = tempfile.NamedTemporaryFile(prefix="video-tts-", suffix=".zip", delete=False)
    temporary.close()
    zip_path = Path(temporary.name)
    try:
        used_names: set[str] = set()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for index, asset in enumerate(ordered, 1):
                path = resolve_asset_path(asset.project_id, asset.relative_path)
                if not path.exists():
                    raise HTTPException(404, f"Không tìm thấy file {asset.display_name}")
                archive_name = path.name
                if archive_name.lower() in used_names:
                    archive_name = f"{path.stem}-{index}{path.suffix}"
                used_names.add(archive_name.lower())
                archive.write(path, arcname=archive_name)
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="video-output.zip",
        background=BackgroundTask(zip_path.unlink, missing_ok=True),
    )
