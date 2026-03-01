import math
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_tenant
from app.clients.openlibrary import OpenLibraryClient
from app.database import get_session
from app.models.reading_list import ReadingList
from app.models.tenant import Tenant
from app.schemas.common import PaginatedResponse
from app.schemas.reading_list import (
    ReadingListItemOut,
    ReadingListOut,
    ReadingListResponse,
    ReadingListSubmission,
)
from app.services.reading_list_service import ReadingListService

router = APIRouter(tags=["reading-lists"])


@router.post("/reading-lists", response_model=ReadingListResponse)
async def submit_reading_list(
    body: ReadingListSubmission,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Submit a patron reading list. PII is hashed before storage."""
    ol_client = OpenLibraryClient()
    try:
        service = ReadingListService(session, ol_client)
        return await service.submit(tenant_id=tenant.id, submission=body)
    finally:
        await ol_client.close()


@router.get("/reading-lists", response_model=PaginatedResponse[ReadingListOut])
async def list_reading_lists(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """List reading lists for a tenant (shows masked PII)."""
    base_filter = ReadingList.tenant_id == tenant.id

    count_result = await session.execute(select(func.count()).where(base_filter).select_from(ReadingList))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(ReadingList)
        .where(base_filter)
        .options(selectinload(ReadingList.items))
        .order_by(ReadingList.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    lists = result.scalars().unique().all()

    items = [
        ReadingListOut(
            id=rl.id,
            patron_name_masked=rl.patron_name_masked,
            email_masked=rl.email_masked,
            items=[ReadingListItemOut.model_validate(item) for item in rl.items],
            created_at=rl.created_at,
            updated_at=rl.updated_at,
        )
        for rl in lists
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/reading-lists/{reading_list_id}", response_model=ReadingListOut)
async def get_reading_list(
    reading_list_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Get a single reading list detail."""
    result = await session.execute(
        select(ReadingList)
        .where(ReadingList.tenant_id == tenant.id, ReadingList.id == reading_list_id)
        .options(selectinload(ReadingList.items))
    )
    rl = result.scalar_one_or_none()
    if rl is None:
        raise HTTPException(status_code=404, detail="Reading list not found")

    return ReadingListOut(
        id=rl.id,
        patron_name_masked=rl.patron_name_masked,
        email_masked=rl.email_masked,
        items=[ReadingListItemOut.model_validate(item) for item in rl.items],
        created_at=rl.created_at,
        updated_at=rl.updated_at,
    )
