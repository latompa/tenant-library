"""Integration tests for reading list endpoints."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.book import Book


@pytest_asyncio.fixture
async def catalog_book(db_session: AsyncSession, tenant):
    """A book already in the tenant's catalog."""
    book = Book(
        tenant_id=tenant.id, ol_work_key="OL27448W",
        title="The Lord of the Rings", first_publish_year=1954,
    )
    db_session.add(book)
    await db_session.commit()
    return book


@pytest.mark.asyncio
async def test_submit_reading_list(client, tenant, catalog_book):
    resp = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Jane Smith",
            "email": "jane@example.com",
            "books": [
                {"ol_work_key": "OL27448W"},  # in catalog
                {"ol_work_key": "OL27482W"},  # valid on OL, not in catalog
            ],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["patron_name_masked"] == "J*** S****"
    assert data["email_masked"] == "j**e@e*****e.com"
    assert data["is_update"] is False
    assert len(data["resolved_books"]) >= 1
    # First book is in catalog (resolved without OL call)
    catalog_resolved = [b for b in data["resolved_books"] if b["found_in_catalog"]]
    assert len(catalog_resolved) == 1
    assert catalog_resolved[0]["ol_work_key"] == "OL27448W"


@pytest.mark.asyncio
async def test_submit_dedup_replaces_items(client, tenant, catalog_book):
    # First submission
    resp1 = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Bob Jones",
            "email": "bob@example.com",
            "books": [{"ol_work_key": "OL27448W"}],
        },
    )
    assert resp1.status_code == 200
    list_id = resp1.json()["reading_list_id"]

    # Second submission — same email, should replace
    resp2 = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Bobby Jones",
            "email": "bob@example.com",
            "books": [{"ol_work_key": "OL27482W"}],
        },
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["reading_list_id"] == list_id  # same list
    assert data["is_update"] is True
    assert data["patron_name_masked"] == "B**** J****"  # updated name

    # Verify only new items remain
    detail = await client.get(f"/api/v1/tenants/{tenant.slug}/reading-lists/{list_id}")
    items = detail.json()["items"]
    assert len(items) == 1
    assert items[0]["ol_work_key"] == "OL27482W"


@pytest.mark.asyncio
async def test_submit_unresolved_book(client, tenant):
    resp = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Test User",
            "email": "test@example.com",
            "books": [{"ol_work_key": "OL99999999W"}],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["unresolved_books"]) == 1
    assert "not found" in data["unresolved_books"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_submit_requires_book_identifier(client, tenant):
    resp = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Test User",
            "email": "test@example.com",
            "books": [{}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_invalid_email(client, tenant):
    resp = await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Test User",
            "email": "not-an-email",
            "books": [{"ol_work_key": "OL27448W"}],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_reading_lists(client, tenant, catalog_book):
    # Submit one
    await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Alice",
            "email": "alice@example.com",
            "books": [{"ol_work_key": "OL27448W"}],
        },
    )
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/reading-lists")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_reading_list_tenant_isolation(client, tenant, tenant_b, catalog_book):
    # Submit to tenant
    await client.post(
        f"/api/v1/tenants/{tenant.slug}/reading-lists",
        json={
            "patron_name": "Isolated User",
            "email": "isolated@example.com",
            "books": [{"ol_work_key": "OL27448W"}],
        },
    )
    # tenant_b should see nothing
    resp = await client.get(f"/api/v1/tenants/{tenant_b.slug}/reading-lists")
    assert resp.json()["total"] == 0
