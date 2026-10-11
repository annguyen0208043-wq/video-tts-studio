from __future__ import annotations

import subprocess

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Project
from app.schemas.api import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.storage_service import create_project_dirs, delete_project_files, project_dir


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name.strip(), settings={})
    db.add(project)
    db.flush()
    create_project_dirs(project.id)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy project")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy project")
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.settings is not None:
        project.settings = payload.settings
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Không tìm thấy project")
    db.delete(project)
    db.commit()
    delete_project_files(project_id)
    return Response(status_code=204)


@router.post("/{project_id}/open-folder", status_code=204)
def open_project_folder(project_id: str, db: Session = Depends(get_db)):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Không tìm thấy project")
    path = create_project_dirs(project_id)
    subprocess.Popen(["explorer.exe", str(path)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return Response(status_code=204)
