"""Celery application with beat schedule for quota reset and maintenance."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "genai_studio",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "reset-daily-quotas": {
        "task": "app.tasks.maintenance_tasks.reset_quotas_task",
        "schedule": crontab(hour=0, minute=0),
    },
    "cleanup-old-images-weekly": {
        "task": "app.tasks.maintenance_tasks.cleanup_old_images_task",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
}

# Register task modules (explicit import ensures worker registers names)
import app.tasks.generation_tasks  # noqa: F401, E402
import app.tasks.maintenance_tasks  # noqa: F401, E402
