"""Seed default tenants into the database."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant

DEFAULT_TENANTS = [
    {"name": "Downtown Public Library", "slug": "downtown-library"},
    {"name": "Westside Branch Library", "slug": "westside-library"},
    {"name": "University Library", "slug": "university-library"},
]


async def seed_tenants(session: AsyncSession) -> None:
    for tenant_data in DEFAULT_TENANTS:
        result = await session.execute(
            select(Tenant).where(Tenant.slug == tenant_data["slug"])
        )
        if result.scalar_one_or_none() is None:
            session.add(Tenant(**tenant_data))
    await session.commit()
