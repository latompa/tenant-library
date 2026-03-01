"""Integration tests for book retrieval endpoints."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.author import Author
from app.models.book import Book, BookAuthor, BookSubject


@pytest_asyncio.fixture
async def seeded_books(db_session: AsyncSession, tenant):
    """Seed some books for testing."""
    author = Author(
        tenant_id=tenant.id, ol_author_key="OL26320A", name="J.R.R. Tolkien",
    )
    db_session.add(author)
    await db_session.flush()

    books_data = [
        ("OL27448W", "The Lord of the Rings", 1954),
        ("OL27482W", "The Hobbit", 1937),
        ("OL27495W", "The Silmarillion", 1977),
    ]
    books = []
    for ol_key, title, year in books_data:
        book = Book(
            tenant_id=tenant.id, ol_work_key=ol_key, title=title,
            first_publish_year=year,
            cover_url=f"https://covers.openlibrary.org/b/id/123-M.jpg",
        )
        db_session.add(book)
        await db_session.flush()
        db_session.add(BookAuthor(book_id=book.id, author_id=author.id))
        db_session.add(BookSubject(book_id=book.id, subject="Fantasy"))
        db_session.add(BookSubject(book_id=book.id, subject="Fiction"))
        books.append(book)

    await db_session.commit()
    return books


@pytest.mark.asyncio
async def test_list_books(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_books_pagination(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books?page=1&page_size=2")
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 3
    assert data["total_pages"] == 2


@pytest.mark.asyncio
async def test_filter_by_year_range(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books?year_from=1950&year_to=1960")
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "The Lord of the Rings"


@pytest.mark.asyncio
async def test_filter_by_subject(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books?subject=Fantasy")
    data = resp.json()
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_keyword_search_title(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books?q=hobbit")
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "The Hobbit"


@pytest.mark.asyncio
async def test_keyword_search_author(client, tenant, seeded_books):
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books?q=tolkien")
    data = resp.json()
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_get_book_detail(client, tenant, seeded_books):
    book_id = seeded_books[0].id
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books/{book_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "The Lord of the Rings"
    assert len(data["authors"]) == 1
    assert data["authors"][0]["name"] == "J.R.R. Tolkien"
    assert "Fantasy" in data["subjects"]


@pytest.mark.asyncio
async def test_get_book_not_found(client, tenant, seeded_books):
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/tenants/{tenant.slug}/books/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation(client, tenant, tenant_b, seeded_books):
    # Books belong to tenant, not tenant_b
    resp = await client.get(f"/api/v1/tenants/{tenant_b.slug}/books")
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_invalid_tenant(client):
    resp = await client.get("/api/v1/tenants/nonexistent/books")
    assert resp.status_code == 404
