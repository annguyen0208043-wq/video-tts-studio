from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Project
from app.schemas.api import ScriptGenerate, ScriptGenerateOut
from app.services.ai_router import AIProviderError, ai_router
from app.services.script_service import generate_scripts
from app.services.skill_loader import list_skills


router = APIRouter(tags=["ai-scripts"])


@router.get("/ai/providers")
def providers():
    return {"default": "auto", "providers": ai_router.providers()}


@router.get("/ai/skills")
def skills():
    return list_skills()


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
