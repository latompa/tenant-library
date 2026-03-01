import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.tenant import Tenant


async def get_current_tenant(
    x_tenant_id: str = Header(..., description="Tenant slug"),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.slug == x_tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{x_tenant_id}' not found")
    return tenant
