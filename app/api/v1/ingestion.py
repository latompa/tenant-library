import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_current_tenant
from app.database import get_session
from app.models.ingestion import IngestionJob
from app.models.tenant import Tenant
from app.schemas.common import PaginatedResponse
from app.schemas.ingestion import IngestionRequest
from app.schemas.job import IngestionJobDetail, IngestionJobResponse

router = APIRouter(tags=["ingestion"])


@router.post("/ingestion", response_model=IngestionJobResponse)
async def trigger_ingestion(
    body: IngestionRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Queue a catalog ingestion job from Open Library by author or subject."""
    from app.tasks.ingestion_tasks import ingest_works

    # Create job record
    job = IngestionJob(
        tenant_id=tenant.id,
        query_type=body.query_type,
        query_value=body.query_value,
        limit=body.limit,
        status="queued",
    )
    session.add(job)
    await session.commit()

    # Queue Celery task
    ingest_works.delay(
        tenant_id=str(tenant.id),
        job_id=str(job.id),
        query_type=body.query_type,
        query_value=body.query_value,
        limit=body.limit,
    )

    return IngestionJobResponse(
        job_id=job.id,
        status="queued",
        message=f"Ingestion job queued for {body.query_type} '{body.query_value}'",
    )


@router.get("/ingestion/jobs", response_model=PaginatedResponse[IngestionJobDetail])
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """List ingestion jobs for a tenant, newest first."""
    base_filter = IngestionJob.tenant_id == tenant.id

    count_result = await session.execute(select(func.count()).where(base_filter).select_from(IngestionJob))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(IngestionJob)
        .where(base_filter)
        .order_by(IngestionJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    jobs = result.scalars().all()

    return PaginatedResponse(
        items=[IngestionJobDetail.model_validate(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/ingestion/jobs/{job_id}", response_model=IngestionJobDetail)
async def get_job(
    job_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Get ingestion job status and progress."""
    result = await session.execute(
        select(IngestionJob).where(IngestionJob.tenant_id == tenant.id, IngestionJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return IngestionJobDetail.model_validate(job)
