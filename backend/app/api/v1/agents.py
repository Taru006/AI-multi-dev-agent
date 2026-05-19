"""
Agents API Router — /api/v1/agents/*
Returns agent states and logs for a project.
"""

import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.agent_state import AgentState
from app.models.task import TaskLog
from app.api.v1.auth import get_current_user

router = APIRouter(prefix="/agents")


@router.get("/{project_id}/states")
async def get_agent_states(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all agent states for a project."""
    result = await db.execute(
        select(AgentState).where(AgentState.project_id == uuid.UUID(project_id))
    )
    states = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "agent_type": s.agent_type,
            "status": s.status,
            "current_task_id": str(s.current_task_id) if s.current_task_id else None,
            "total_tokens_used": s.total_tokens_used,
            "last_active": s.last_active.isoformat(),
        }
        for s in states
    ]


@router.get("/{project_id}/logs")
async def get_agent_logs(
    project_id: str,
    agent_type: str = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return task logs for a project, optionally filtered by agent type."""
    query = (
        select(TaskLog)
        .join(TaskLog.task)
        .where(TaskLog.task.has(project_id=uuid.UUID(project_id)))
        .order_by(TaskLog.timestamp.desc())
        .limit(limit)
    )
    if agent_type:
        query = query.where(TaskLog.agent_type == agent_type)

    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "task_id": str(log.task_id),
            "agent_type": log.agent_type,
            "level": log.level,
            "message": log.message,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]
