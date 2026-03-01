from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant
from app.database import get_session
from app.models.tenant import Tenant
from app.schemas.book import BookDetail, BookSummary
from app.schemas.common import PaginatedResponse
from app.services.book_service import BookService

router = APIRouter(tags=["books"])


@router.get("/books", response_model=PaginatedResponse[BookSummary])
async def list_books(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    author: str | None = Query(default=None, description="Filter by author name"),
    subject: str | None = Query(default=None, description="Filter by subject"),
    year_from: int | None = Query(default=None, description="Min publish year"),
    year_to: int | None = Query(default=None, description="Max publish year"),
    q: str | None = Query(default=None, description="Keyword search (title or author)"),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """List books with pagination, filtering, and keyword search."""
    service = BookService(session)
    return await service.list_books(
        tenant_id=tenant.id,
        page=page,
        page_size=page_size,
        author=author,
        subject=subject,
        year_from=year_from,
        year_to=year_to,
        q=q,
    )


@router.get("/books/{book_id}", response_model=BookDetail)
async def get_book(
    book_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    """Get a single book's full detail."""
    service = BookService(session)
    book = await service.get_book(tenant_id=tenant.id, book_id=book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book
