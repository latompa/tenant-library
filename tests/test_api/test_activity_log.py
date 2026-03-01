"""Integration tests for activity log endpoint."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestionLog


@pytest_asyncio.fixture
async def seeded_logs(db_session: AsyncSession, tenant):
    for i in range(3):
        log = IngestionLog(
            tenant_id=tenant.id,
            query_type="author",
            query_value=f"author_{i}",
            works_fetched=10,
            works_stored=8,
            works_failed=2,
            status="completed",
        )
        db_session.add(log)
    await db_session.commit()


@pytest.mark.asyncio
async def test_list_activity_log(client, tenant, seeded_logs):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/activity-log")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_activity_log_pagination(client, tenant, seeded_logs):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/activity-log?page=1&page_size=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total_pages"] == 2


@pytest.mark.asyncio
async def test_activity_log_tenant_isolation(client, tenant, tenant_b, seeded_logs):
    resp = await client.get(f"/api/v1/tenants/{tenant_b.slug}/activity-log")
    assert resp.json()["total"] == 0
