from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BgmTrack
from app.schemas.api import BgmTrackOut, BgmTrackUpdate
from app.services.media_probe import AUDIO_EXTENSIONS, probe
from app.services.storage_service import bgm_library_dir, safe_filename, unique_destination


router = APIRouter(tags=["bgm"])


@router.post("/bgm/upload", response_model=list[BgmTrackOut], status_code=201)
def upload_bgm(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Upload one or more audio files to the global BGM library."""
    library = bgm_library_dir()
    library.mkdir(parents=True, exist_ok=True)
    created: list[BgmTrack] = []
    for upload in files:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in AUDIO_EXTENSIONS:
            raise HTTPException(415, f"Định dạng không hỗ trợ: {suffix or upload.filename}")
        destination = unique_destination(library, upload.filename or f"bgm{suffix}")
        size = 0
        try:
            with destination.open("wb") as target:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 500 * 1024 * 1024:  # 500MB limit for BGM
                        raise HTTPException(413, "File vượt 500 MB")
                    target.write(chunk)
            info = probe(destination)
            track = BgmTrack(
                display_name=Path(upload.filename or destination.name).stem,
                relative_path=destination.name,
                duration_ms=info["duration_ms"],
                codec=info["codec"],
                file_size=size,
            )
            db.add(track)
            created.append(track)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            upload.file.close()
    db.commit()
    for track in created:
        db.refresh(track)
    return created


@router.get("/bgm", response_model=list[BgmTrackOut])
def list_bgm(db: Session = Depends(get_db)):
    """List all tracks in the global BGM library."""
    return db.scalars(select(BgmTrack).order_by(BgmTrack.created_at.desc())).all()


@router.get("/bgm/{track_id}/stream")
def stream_bgm(track_id: str, db: Session = Depends(get_db)):
    """Stream a BGM track for playback."""
    track = db.get(BgmTrack, track_id)
    if not track:
        raise HTTPException(404, "Không tìm thấy nhạc nền")
    path = bgm_library_dir() / track.relative_path
    if not path.exists():
        raise HTTPException(404, "File nhạc nền không còn tồn tại")
    db.close()
    return FileResponse(path, filename=path.name)


@router.patch("/bgm/{track_id}", response_model=BgmTrackOut)
def update_bgm(track_id: str, payload: BgmTrackUpdate, db: Session = Depends(get_db)):
    """Rename or tag a BGM track."""
    track = db.get(BgmTrack, track_id)
    if not track:
        raise HTTPException(404, "Không tìm thấy nhạc nền")
    if payload.display_name is not None:
        track.display_name = payload.display_name
    if payload.tags is not None:
        track.tags = payload.tags
    db.commit()
    db.refresh(track)
    return track


@router.delete("/bgm/{track_id}", status_code=204)
def delete_bgm(track_id: str, db: Session = Depends(get_db)):
    """Delete a BGM track from the library."""
    track = db.get(BgmTrack, track_id)
    if not track:
        raise HTTPException(404, "Không tìm thấy nhạc nền")
    path = bgm_library_dir() / track.relative_path
    db.delete(track)
    db.commit()
    path.unlink(missing_ok=True)
    return Response(status_code=204)
