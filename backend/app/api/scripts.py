from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Project
from app.schemas.api import ScriptGenerate, ScriptGenerateOut, SkillUpdate
from app.services.ai_router import AIProviderError, ai_router
from app.services.script_service import generate_scripts
from app.services.skill_loader import (
    delete_skill, install_skill, list_skills, load_skill, skill_dict,
    skill_template_markdown, update_skill,
)


router = APIRouter(tags=["ai-scripts"])


@router.get("/ai/providers")
def providers():
    return {"default": "auto", "providers": ai_router.providers()}


@router.get("/ai/skills")
def skills():
    return list_skills()


@router.get("/ai/skills/template")
def download_skill_template():
    return StreamingResponse(
        BytesIO(skill_template_markdown()),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="SKILL_MAU_KICH_BAN_LINH_HOAT.md"'},
    )


@router.post("/ai/skills", status_code=201)
async def upload_skill(file: UploadFile = File(...)):
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".md", ".markdown"}:
        raise HTTPException(400, "Vui lòng tải lên file Skill .md hoặc .markdown")
    try:
        return install_skill(await file.read(), filename)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/ai/skills/{skill_id}")
def skill_detail(skill_id: str):
    try:
        return skill_dict(load_skill(skill_id), include_content=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/ai/skills/{skill_id}")
def save_skill(skill_id: str, payload: SkillUpdate):
    try:
        return update_skill(skill_id, payload.content, payload.name)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/ai/skills/{skill_id}", status_code=204)
def remove_skill(skill_id: str):
    try:
        delete_skill(skill_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/projects/{project_id}/scripts/generate", response_model=ScriptGenerateOut)
def generate(project_id: str, payload: ScriptGenerate, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    try:
        return generate_scripts(payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(503, str(exc)) from exc
