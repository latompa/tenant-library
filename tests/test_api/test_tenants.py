"""Integration tests for tenant management endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_tenant(client):
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "New Library", "slug": "new-library"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "New Library"
    assert data["slug"] == "new-library"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_tenant_duplicate_slug(client):
    await client.post(
        "/api/v1/tenants",
        json={"name": "Library A", "slug": "dupe-slug"},
    )
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Library B", "slug": "dupe-slug"},
    )
    assert resp.status_code == 409
    assert "slug" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_tenant_duplicate_name(client):
    await client.post(
        "/api/v1/tenants",
        json={"name": "Same Name", "slug": "slug-one"},
    )
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Same Name", "slug": "slug-two"},
    )
    assert resp.status_code == 409
    assert "name" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_tenant_invalid_slug(client):
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Bad Slug", "slug": "Has Spaces"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_tenants(client):
    await client.post(
        "/api/v1/tenants",
        json={"name": "Alpha Library", "slug": "alpha-library"},
    )
    await client.post(
        "/api/v1/tenants",
        json={"name": "Beta Library", "slug": "beta-library"},
    )
    resp = await client.get("/api/v1/tenants")
    assert resp.status_code == 200
    slugs = [t["slug"] for t in resp.json()]
    assert "alpha-library" in slugs
    assert "beta-library" in slugs
