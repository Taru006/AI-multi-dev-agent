"""
Celery Application Configuration
Broker: Redis (separate DB from cache)
Backend: Redis
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "ai_dev_agency",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.agent_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (LLM calls are expensive)
    task_routes={
        "app.workers.agent_tasks.run_project_workflow": {"queue": "workflows"},
        "app.workers.agent_tasks.run_single_agent_task": {"queue": "agents"},
    },
    beat_schedule={},  # Add scheduled tasks here
)
