from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api import assets, bgm, jobs, projects, scripts, sequences, system
from app.core.config import ROOT_DIR, settings
from app.core.logging import configure_logging
from app.db.session import Base, SessionLocal, engine
from app.models import Job
from app.services.job_service import job_manager
from app.services.storage_service import ensure_storage


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    ensure_storage()
    Base.metadata.create_all(bind=engine)
    # A process restart cannot keep ownership of an old FFmpeg/TTS process.
    # Mark interrupted work clearly and resume jobs that never started.
    with SessionLocal() as db:
        interrupted = db.scalars(
            select(Job).where(Job.status.in_({"running", "rendering", "processing"}))
        ).all()
        for job in interrupted:
            job.status = "failed"
            job.error_message = "Tác vụ bị gián đoạn do ứng dụng khởi động lại; hãy bấm Thử lại."
        queued = [job.id for job in db.scalars(select(Job).where(Job.status == "queued")).all()]
        db.commit()
    for job_id in queued:
        job_manager.submit(job_id)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(assets.router, prefix="/api")
app.include_router(sequences.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(scripts.router, prefix="/api")
app.include_router(bgm.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "name": settings.app_name}


frontend_dist = ROOT_DIR / "frontend" / "dist"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        requested = (frontend_dist / path).resolve()
        if path and requested.is_file() and frontend_dist.resolve() in requested.parents:
            return FileResponse(requested)
        return FileResponse(frontend_dist / "index.html")
