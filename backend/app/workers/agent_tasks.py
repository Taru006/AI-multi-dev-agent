"""
Celery Tasks — Background agent workflow execution.
These tasks are enqueued by the API and run by Celery workers.
"""

import asyncio
import structlog

from app.workers.celery_app import celery_app
from app.config import settings

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.agent_tasks.run_project_workflow",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_project_workflow(self, project_id: str, project_data: dict):
    """
    Main Celery task: runs the complete multi-agent workflow for a project.
    This task is long-running (minutes to hours depending on project size).
    """
    log = logger.bind(project_id=project_id, task_id=self.request.id)
    log.info("Celery workflow task started")

    try:
        # Run async workflow in sync Celery task context
        asyncio.run(_run_workflow_async(project_id, project_data))
        log.info("Workflow completed successfully")
    except Exception as exc:
        log.error("Workflow failed", error=str(exc))
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            log.error("Max retries exceeded, workflow permanently failed")
            _mark_project_failed(project_id, str(exc))


async def _run_workflow_async(project_id: str, project_data: dict):
    """Initialize DB, WebSocket manager, and start the workflow engine."""
    from app.db.session import AsyncSessionLocal
    from app.messaging.websocket_manager import WebSocketManager
    from app.orchestrator.workflow_engine import WorkflowEngine

    # Create a simple WebSocket manager (no real connections in worker)
    class WorkerWsManager:
        """Stub WS manager for Celery worker (broadcasts to Redis instead)."""
        async def broadcast_to_project(self, project_id: str, message: dict):
            # In production, publish to Redis so API servers can relay to clients
            import redis.asyncio as aioredis
            import json
            r = aioredis.from_url(settings.REDIS_URL)
            await r.publish(
                f"ws:project:{project_id}",
                json.dumps(message, default=str),
            )
            await r.aclose()

    ws_manager = WorkerWsManager()

    async with AsyncSessionLocal() as db:
        engine = WorkflowEngine(
            project_id=project_id,
            ws_manager=ws_manager,
            db_session=db,
        )
        await engine.start_workflow(project_data)


def _mark_project_failed(project_id: str, error: str):
    """Synchronously mark project as failed in DB."""
    async def _async_mark():
        from app.db.session import AsyncSessionLocal
        from app.models.project import Project
        from sqlalchemy import select, update

        async with AsyncSessionLocal() as db:
            import uuid
            await db.execute(
                update(Project)
                .where(Project.id == uuid.UUID(project_id))
                .values(status="failed")
            )
            await db.commit()

    asyncio.run(_async_mark())


@celery_app.task(name="app.workers.agent_tasks.run_single_agent_task")
def run_single_agent_task(project_id: str, agent_type: str, task_data: dict):
    """Run a single agent task (used for retries or manual triggers)."""
    asyncio.run(_run_single_agent(project_id, agent_type, task_data))


async def _run_single_agent(project_id: str, agent_type: str, task_data: dict):
    """Execute a single agent task."""
    from app.orchestrator.workflow_engine import AGENT_CLASSES
    from app.messaging.event_bus import EventBus

    AgentClass = AGENT_CLASSES.get(agent_type)
    if not AgentClass:
        logger.error("Unknown agent type", agent_type=agent_type)
        return

    event_bus = EventBus(project_id=project_id)
    agent = AgentClass(project_id=project_id, event_bus=event_bus)
    result = await agent.run(task_data)
    logger.info("Single agent task complete", agent_type=agent_type, success=result.get("success"))
