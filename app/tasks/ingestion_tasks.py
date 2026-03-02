"""Celery tasks for catalog ingestion."""

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine in a new event loop (for Celery's sync workers)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3)
def ingest_works(self, tenant_id: str, job_id: str, query_type: str, query_value: str, limit: int = 50):
    """Main ingestion task. Runs the async pipeline inside Celery's sync worker."""
    _run_async(_ingest_works_async(self, tenant_id, job_id, query_type, query_value, limit))


async def _ingest_works_async(task, tenant_id: str, job_id: str, query_type: str, query_value: str, limit: int):
    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.clients.openlibrary import OpenLibraryClient
    from app.config import settings
    from app.models.ingestion import IngestionJob
    from app.services.ingestion_service import IngestionService

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    job_uuid = uuid.UUID(job_id)

    async with session_factory() as session:
        ol_client = OpenLibraryClient()
        try:
            # Update job to running
            result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_uuid))
            job = result.scalar_one()
            job.status = "running"
            job.celery_task_id = task.request.id
            await session.commit()

            # Run ingestion, linking the log back to the job
            service = IngestionService(session, ol_client)
            log = await service.ingest(
                tenant_id=uuid.UUID(tenant_id),
                query_type=query_type,
                query_value=query_value,
                limit=limit,
                job_id=job_uuid,
            )

            # Update job with results
            await session.refresh(job)
            job.status = "completed" if log.status == "completed" else "failed"
            job.progress = {
                "works_fetched": log.works_fetched,
                "works_stored": log.works_stored,
                "works_failed": log.works_failed,
            }
            if log.error_message:
                job.error_message = log.error_message
            await session.commit()

            logger.info(f"Ingestion completed: {log.works_stored} stored, {log.works_failed} failed")

        except Exception as exc:
            try:
                result = await session.execute(select(IngestionJob).where(IngestionJob.id == job_uuid))
                job = result.scalar_one()
                job.status = "failed"
                job.error_message = str(exc)[:2000]
                await session.commit()
            except Exception:
                logger.exception("Failed to update job status")

            logger.exception(f"Ingestion task failed for job {job_id}")
            # Exponential backoff: 60s, 120s, 240s
            backoff = 60 * (2 ** task.request.retries)
            raise task.retry(exc=exc, countdown=backoff)

        finally:
            await ol_client.close()

    await engine.dispose()


@celery_app.task
def run_fair_dispatch():
    """Periodic task: dispatch queued tasks fairly across tenants."""
    from app.tasks.fair_scheduler import dispatch_fair_batch

    dispatched = dispatch_fair_batch()
    if dispatched:
        logger.info("Fair dispatch: sent %d task(s) to Celery", dispatched)


@celery_app.task
def refresh_all_catalogs():
    """Periodic task: re-run recent ingestion queries to keep catalogs fresh."""
    _run_async(_refresh_all_catalogs_async())


async def _refresh_all_catalogs_async():
    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models.ingestion import IngestionJob, IngestionLog

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Get distinct (tenant_id, query_type, query_value) from completed logs
        result = await session.execute(
            select(
                IngestionLog.tenant_id,
                IngestionLog.query_type,
                IngestionLog.query_value,
            )
            .where(IngestionLog.status == "completed")
            .distinct()
        )
        queries = result.all()

        for tenant_id, query_type, query_value in queries:
            # Create a job record for tracking
            job = IngestionJob(
                tenant_id=tenant_id,
                query_type=query_type,
                query_value=query_value,
                limit=50,
                status="queued",
            )
            session.add(job)
            await session.flush()

            from app.tasks.fair_scheduler import enqueue_task

            enqueue_task(
                tenant_id=str(tenant_id),
                task_name="app.tasks.ingestion_tasks.ingest_works",
                kwargs={
                    "tenant_id": str(tenant_id),
                    "job_id": str(job.id),
                    "query_type": query_type,
                    "query_value": query_value,
                    "limit": 50,
                },
            )
            logger.info(f"Queued refresh: {query_type}={query_value} for tenant {tenant_id}")

        await session.commit()

    await engine.dispose()
