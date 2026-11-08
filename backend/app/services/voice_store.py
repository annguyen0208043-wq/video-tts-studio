"""Durable voice data; audio columns are never loaded when listing voices."""

from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models import VoiceEntry


def seed(entries: list[dict]) -> None:
    if not entries:
        return
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        # Existing names, embeddings and samples are authoritative. Restarting
        # must not overwrite a renamed clone or copy its audio again.
        for entry in entries:
            db.execute(insert(VoiceEntry).values(**entry).on_conflict_do_nothing(index_elements=["id"]))
        db.commit()


def catalog(custom: bool | None = None) -> list[dict]:
    with SessionLocal() as db:
        statement = select(
            VoiceEntry.id, VoiceEntry.label, VoiceEntry.custom, VoiceEntry.preview_key,
            VoiceEntry.preview_audio.is_not(None).label("has_preview"),
        ).order_by(VoiceEntry.created_at, VoiceEntry.id)
        if custom is not None:
            statement = statement.where(VoiceEntry.custom == custom)
        return [dict(row) for row in db.execute(statement).mappings()]


def definition(voice_id: str) -> dict | None:
    with SessionLocal() as db:
        row = db.execute(select(VoiceEntry.label, VoiceEntry.custom, VoiceEntry.payload).where(VoiceEntry.id == voice_id)).mappings().first()
        return dict(row) if row else None


def rename(voice_id: str, label: str, name: str) -> None:
    with SessionLocal() as db:
        row = db.get(VoiceEntry, voice_id)
        if row is None or not row.custom:
            raise FileNotFoundError("Không tìm thấy giọng clone")
        row.label = label
        row.payload = {**row.payload, "name": name}
        db.commit()


def save_previews(samples: list[tuple[str, str, bytes]]) -> None:
    with SessionLocal() as db:
        for voice_id, key, audio in samples:
            db.execute(update(VoiceEntry).where(VoiceEntry.id == voice_id).values(preview_key=key, preview_audio=audio))
        db.commit()


def preview(key: str) -> bytes | None:
    with SessionLocal() as db:
        return db.scalar(select(VoiceEntry.preview_audio).where(VoiceEntry.preview_key == key))


def has_preview(voice_id: str, key: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(VoiceEntry.id).where(
            VoiceEntry.id == voice_id, VoiceEntry.preview_key == key, VoiceEntry.preview_audio.is_not(None),
        )) is not None
