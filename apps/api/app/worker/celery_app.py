from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "repopilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_time_limit=900,
    task_soft_time_limit=840,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    beat_schedule={
        "repopilot.workspace.cleanup": {
            "task": "repopilot.workspace.cleanup",
            "schedule": settings.workspace_cleanup_interval_seconds,
        },
        "repopilot.artifacts.retention_cleanup": {
            "task": "repopilot.artifacts.retention_cleanup",
            "schedule": settings.artifact_retention_interval_seconds,
        },
        "repopilot.github.reconcile_dispatch": {
            "task": "repopilot.github.reconcile_dispatch",
            "schedule": settings.webhook_dispatch_retry_interval_seconds,
        },
        "repopilot.run.reconcile_stale": {
            "task": "repopilot.run.reconcile_stale",
            "schedule": settings.run_orchestration_reconcile_interval_seconds,
        },
    },
)
