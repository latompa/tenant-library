"""Tenant management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    session: AsyncSession = Depends(get_session),
):
    # Check for duplicate slug or name
    result = await session.execute(
        select(Tenant).where((Tenant.slug == body.slug) | (Tenant.name == body.name))
    )
    existing = result.scalar_one_or_none()
    if existing:
        field = "slug" if existing.slug == body.slug else "name"
        raise HTTPException(status_code=409, detail=f"Tenant with this {field} already exists")

    tenant = Tenant(name=body.name, slug=body.slug)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)
    return tenant


@router.get("", response_model=list[TenantResponse])
async def list_tenants(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Tenant).order_by(Tenant.created_at))
    return result.scalars().all()
