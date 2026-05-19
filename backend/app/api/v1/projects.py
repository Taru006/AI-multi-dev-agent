"""
Projects API Router — /api/v1/projects/*
Manages project lifecycle: create, list, detail, start workflow, approve gates.
"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.artifact import Artifact, ApprovalRequest
from app.api.v1.auth import get_current_user
from app.workers.agent_tasks import run_project_workflow

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/projects")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: str
    requirements: str = ""
    tech_stack: dict = {}
    constraints: str = ""
    timeline: str = "4 weeks"
    github_repo: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    github_repo: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ApprovalDecision(BaseModel):
    decision: str  # "approved" | "rejected"
    comment: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new project. Does NOT start the workflow yet."""
    project = Project(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        tech_stack=payload.tech_stack,
        constraints=payload.constraints,
        timeline=payload.timeline,
        github_repo=payload.github_repo,
        status="pending",
    )
    db.add(project)
    await db.flush()

    logger.info("Project created", project_id=str(project.id), user=str(current_user.id))
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status,
        github_repo=project.github_repo,
        created_at=project.created_at.isoformat(),
    )


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all projects for the current user."""
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [
        ProjectResponse(
            id=str(p.id),
            name=p.name,
            description=p.description,
            status=p.status,
            github_repo=p.github_repo,
            created_at=p.created_at.isoformat(),
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get project details."""
    project = await _get_project_or_404(db, project_id, current_user.id)
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        status=project.status,
        github_repo=project.github_repo,
        created_at=project.created_at.isoformat(),
    )


@router.post("/{project_id}/start")
async def start_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Kick off the multi-agent workflow for a project.
    Enqueues a Celery task and returns immediately.
    """
    project = await _get_project_or_404(db, project_id, current_user.id)

    if project.status not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot start project in status '{project.status}'")

    # Update status
    project.status = "running"
    await db.flush()

    # Enqueue Celery task
    project_data = {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "requirements": "",  # Could be stored separately
        "tech_stack": project.tech_stack,
        "constraints": project.constraints,
        "timeline": project.timeline,
    }
    run_project_workflow.delay(str(project.id), project_data)

    logger.info("Project workflow started", project_id=project_id)
    return {"message": "Workflow started", "project_id": project_id, "status": "running"}


@router.get("/{project_id}/tasks")
async def get_project_tasks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all tasks for a project."""
    await _get_project_or_404(db, project_id, current_user.id)
    result = await db.execute(
        select(Task)
        .where(Task.project_id == uuid.UUID(project_id))
        .order_by(Task.created_at.asc())
    )
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "title": t.title,
            "agent_type": t.agent_type,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


@router.get("/{project_id}/artifacts")
async def get_project_artifacts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all generated artifacts for a project."""
    await _get_project_or_404(db, project_id, current_user.id)
    result = await db.execute(
        select(Artifact)
        .where(Artifact.project_id == uuid.UUID(project_id))
        .order_by(Artifact.created_at.desc())
    )
    artifacts = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "artifact_type": a.artifact_type,
            "name": a.name,
            "file_path": a.file_path,
            "content_preview": a.content_preview,
            "created_at": a.created_at.isoformat(),
        }
        for a in artifacts
    ]


@router.post("/{project_id}/approve/{approval_id}")
async def decide_approval(
    project_id: str,
    approval_id: str,
    payload: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Human-in-the-loop: approve or reject an agent's pending request."""
    result = await db.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == uuid.UUID(approval_id),
            ApprovalRequest.project_id == uuid.UUID(project_id),
        )
    )
    approval = result.scalar_one_or_none()

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != "pending":
        raise HTTPException(status_code=400, detail=f"Already decided: {approval.status}")

    from datetime import datetime, timezone
    approval.status = payload.decision
    approval.decided_by = current_user.id
    approval.decided_at = datetime.now(timezone.utc)

    logger.info("Approval decided", approval_id=approval_id, decision=payload.decision)
    return {"message": f"Approval {payload.decision}", "approval_id": approval_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_or_404(db: AsyncSession, project_id: str, user_id) -> Project:
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    result = await db.execute(
        select(Project).where(Project.id == pid, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
