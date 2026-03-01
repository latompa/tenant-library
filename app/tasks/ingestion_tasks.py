from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ingest_works(self, tenant_id: str, job_id: str, query_type: str, query_value: str, limit: int = 50):
    """Main ingestion task. Implementation added in Phase 5."""
    pass


@celery_app.task
def refresh_all_catalogs():
    """Periodic catalog refresh. Implementation added in Phase 5."""
    pass
