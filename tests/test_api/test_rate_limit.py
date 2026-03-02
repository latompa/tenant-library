"""Tests for per-tenant API rate limiting middleware."""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_session
from app.main import app


@pytest_asyncio.fixture
async def rl_client(db_session, tenant, tenant_b):
    """Client fixture that also ensures tenants exist."""
    app.dependency_overrides[get_session] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def _flush_rate_limit_keys():
    """Clear rate limit keys before each test."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys = await r.keys("ratelimit:*")
        if keys:
            await r.delete(*keys)
    finally:
        await r.aclose()
    yield
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys = await r.keys("ratelimit:*")
        if keys:
            await r.delete(*keys)
    finally:
        await r.aclose()


@pytest.mark.asyncio
async def test_rate_limit_headers_present(rl_client, tenant):
    """Tenant-scoped requests should include rate limit headers."""
    resp = await rl_client.get(f"/api/v1/tenants/{tenant.slug}/books")
    assert "X-RateLimit-Limit" in resp.headers
    assert "X-RateLimit-Remaining" in resp.headers
    assert "X-RateLimit-Reset" in resp.headers
    assert resp.headers["X-RateLimit-Limit"] == str(settings.RATE_LIMIT_PER_MINUTE)


@pytest.mark.asyncio
async def test_rate_limit_429_when_exceeded(rl_client, tenant):
    """Exceeding the limit should return 429."""
    # Pre-fill the counter to just under the limit
    import redis.asyncio as aioredis
    import time

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        now_minute = int(time.time()) // 60
        key = f"ratelimit:{tenant.slug}:{now_minute}"
        await r.set(key, str(settings.RATE_LIMIT_PER_MINUTE), ex=60)
    finally:
        await r.aclose()

    resp = await rl_client.get(f"/api/v1/tenants/{tenant.slug}/books")
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json()["detail"] == "Rate limit exceeded"


@pytest.mark.asyncio
async def test_rate_limit_per_tenant_isolation(rl_client, tenant, tenant_b):
    """Exhausting tenant A's limit should not affect tenant B."""
    import redis.asyncio as aioredis
    import time

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        now_minute = int(time.time()) // 60
        key = f"ratelimit:{tenant.slug}:{now_minute}"
        await r.set(key, str(settings.RATE_LIMIT_PER_MINUTE), ex=60)
    finally:
        await r.aclose()

    # Tenant A should be blocked
    resp_a = await rl_client.get(f"/api/v1/tenants/{tenant.slug}/books")
    assert resp_a.status_code == 429

    # Tenant B should still be fine
    resp_b = await rl_client.get(f"/api/v1/tenants/{tenant_b.slug}/books")
    assert resp_b.status_code != 429


@pytest.mark.asyncio
async def test_non_tenant_routes_not_rate_limited(rl_client):
    """Health and tenant-list routes should not be rate limited."""
    resp = await rl_client.get("/health")
    assert "X-RateLimit-Limit" not in resp.headers
    assert resp.status_code == 200

    resp = await rl_client.get("/api/v1/tenants")
    assert "X-RateLimit-Limit" not in resp.headers


@pytest.mark.asyncio
async def test_rate_limit_remaining_decreases(rl_client, tenant):
    """X-RateLimit-Remaining should decrease with each request."""
    resp1 = await rl_client.get(f"/api/v1/tenants/{tenant.slug}/books")
    rem1 = int(resp1.headers["X-RateLimit-Remaining"])

    resp2 = await rl_client.get(f"/api/v1/tenants/{tenant.slug}/books")
    rem2 = int(resp2.headers["X-RateLimit-Remaining"])

    assert rem2 < rem1
