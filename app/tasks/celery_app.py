from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "tenant_library",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.ingestion_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "refresh-catalogs": {
            "task": "app.tasks.ingestion_tasks.refresh_all_catalogs",
            "schedule": crontab(hour=3, minute=0),
        },
        "fair-dispatch": {
            "task": "app.tasks.ingestion_tasks.run_fair_dispatch",
            "schedule": 5.0,
        },
    },
)
