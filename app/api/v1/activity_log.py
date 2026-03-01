import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.database import get_session
from app.models.ingestion import IngestionLog
from app.models.tenant import Tenant
from app.schemas.common import PaginatedResponse
from app.schemas.ingestion import IngestionLogEntry

router = APIRouter(tags=["activity-log"])


@router.get("/activity-log", response_model=PaginatedResponse[IngestionLogEntry])
async def list_activity_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """List ingestion activity logs for a tenant, newest first."""
    base_filter = IngestionLog.tenant_id == tenant.id

    # Count
    count_result = await session.execute(select(func.count()).where(base_filter).select_from(IngestionLog))
    total = count_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    result = await session.execute(
        select(IngestionLog)
        .where(base_filter)
        .order_by(IngestionLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    logs = result.scalars().all()

    return PaginatedResponse(
        items=[IngestionLogEntry.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )
