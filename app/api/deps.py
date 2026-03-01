from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.tenant import Tenant


async def get_current_tenant(
    tenant_slug: str = Path(..., description="Tenant slug"),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_slug}' not found")
    return tenant
