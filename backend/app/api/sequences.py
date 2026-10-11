from __future__ import annotations

import string

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models import Asset, Project, Sequence, SequenceItem
from app.schemas.api import SequenceGenerate, SequenceManual, SequenceOut, SequenceUpdate
from app.services.sequence_engine import SequenceLimitError, generate_sequences


router = APIRouter(tags=["sequences"])


def _video_assets(
    ids: list[str], project_id: str, db: Session, batch_name: str
) -> dict[str, Asset]:
    assets = db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.project_id == project_id)).all()
    mapping = {asset.id: asset for asset in assets if asset.type == "video"}
    if len(mapping) != len(set(ids)):
        raise HTTPException(400, "Một hoặc nhiều video không hợp lệ")
    wrong_batch = [
        asset.display_name
        for asset in mapping.values()
        if asset.video_batch_name is not None and asset.video_batch_name != batch_name
    ]
    if wrong_batch:
        raise HTTPException(
            400,
            "Video chỉ được thuộc một batch. Hãy gán đúng batch trước: "
            + ", ".join(wrong_batch),
        )
    for asset in mapping.values():
        if asset.video_batch_name is None:
            asset.video_batch_name = batch_name
    return mapping


def _loaded_sequences(project_id: str, db: Session):
    return db.scalars(
        select(Sequence)
        .where(Sequence.project_id == project_id)
        .options(selectinload(Sequence.items).selectinload(SequenceItem.asset))
        .order_by(Sequence.created_at.desc())
    ).all()


@router.get("/projects/{project_id}/sequences", response_model=list[SequenceOut])
def list_sequences(project_id: str, db: Session = Depends(get_db)):
    return _loaded_sequences(project_id, db)


@router.post("/projects/{project_id}/sequences/manual", response_model=SequenceOut, status_code=201)
def manual_sequence(project_id: str, payload: SequenceManual, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    _video_assets(payload.video_asset_ids, project_id, db, payload.batch_name)
    sequence = Sequence(project_id=project_id, name=payload.name, batch_name=payload.batch_name, enabled=True)
    db.add(sequence)
    db.flush()
    for position, asset_id in enumerate(payload.video_asset_ids):
        db.add(SequenceItem(sequence_id=sequence.id, asset_id=asset_id, position=position))
    db.commit()
    return db.scalar(
        select(Sequence)
        .where(Sequence.id == sequence.id)
        .options(selectinload(Sequence.items).selectinload(SequenceItem.asset))
    )


@router.post("/projects/{project_id}/sequences/generate", response_model=list[SequenceOut], status_code=201)
def generate(project_id: str, payload: SequenceGenerate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    _video_assets(payload.video_asset_ids, project_id, db, payload.batch_name)
    limit = min(payload.limit, settings.max_sequence_outputs)
    try:
        generated = generate_sequences(payload.video_asset_ids, payload.mode, payload.length, limit)
    except (ValueError, SequenceLimitError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if payload.replace_existing:
        existing = db.scalars(select(Sequence).where(Sequence.project_id == project_id, Sequence.batch_name == payload.batch_name)).all()
        for sequence in existing:
            db.delete(sequence)
        db.flush()
    labels = {asset_id: string.ascii_uppercase[i] if i < 26 else str(i + 1) for i, asset_id in enumerate(payload.video_asset_ids)}
    created_ids = []
    for values in generated:
        name = "-".join(labels[value] for value in values)
        sequence = Sequence(project_id=project_id, name=name, batch_name=payload.batch_name, enabled=True)
        db.add(sequence)
        db.flush()
        created_ids.append(sequence.id)
        for position, asset_id in enumerate(values):
            db.add(SequenceItem(sequence_id=sequence.id, asset_id=asset_id, position=position))
    db.commit()
    return db.scalars(
        select(Sequence)
        .where(Sequence.id.in_(created_ids))
        .options(selectinload(Sequence.items).selectinload(SequenceItem.asset))
    ).all()


@router.patch("/sequences/{sequence_id}", response_model=SequenceOut)
def update_sequence(sequence_id: str, payload: SequenceUpdate, db: Session = Depends(get_db)):
    sequence = db.get(Sequence, sequence_id)
    if not sequence:
        raise HTTPException(404, "Không tìm thấy sequence")
    if payload.name is not None:
        sequence.name = payload.name.strip()
    if payload.enabled is not None:
        sequence.enabled = payload.enabled
    db.commit()
    return db.scalar(
        select(Sequence)
        .where(Sequence.id == sequence_id)
        .options(selectinload(Sequence.items).selectinload(SequenceItem.asset))
    )


@router.delete("/sequences/{sequence_id}", status_code=204)
def delete_sequence(sequence_id: str, db: Session = Depends(get_db)):
    sequence = db.get(Sequence, sequence_id)
    if not sequence:
        raise HTTPException(404, "Không tìm thấy sequence")
    db.delete(sequence)
    db.commit()
    return Response(status_code=204)


@router.delete("/projects/{project_id}/sequence-batches/{batch_name}")
def delete_sequence_batch(project_id: str, batch_name: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    sequences = db.scalars(
        select(Sequence).where(
            Sequence.project_id == project_id,
            Sequence.batch_name == batch_name,
        )
    ).all()
    if not sequences:
        raise HTTPException(404, "Không tìm thấy batch")
    for sequence in sequences:
        db.delete(sequence)
    videos = db.scalars(
        select(Asset).where(
            Asset.project_id == project_id,
            Asset.type == "video",
            Asset.video_batch_name == batch_name,
        )
    ).all()
    for video in videos:
        video.video_batch_name = None
    db.commit()
    return {"deleted_sequences": len(sequences), "released_videos": len(videos)}
