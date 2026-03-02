"""Book query, filtering, and search logic."""

import math
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.author import Author
from app.models.book import Book, BookAuthor, BookSubject
from app.schemas.book import AuthorSummary, BookDetail, BookSummary
from app.schemas.common import PaginatedResponse


class BookService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_books(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        author: str | None = None,
        subject: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        q: str | None = None,
    ) -> PaginatedResponse[BookSummary]:
        base = select(Book).where(Book.tenant_id == tenant_id)

        # Filter by author name (case-insensitive contains)
        if author:
            base = base.where(
                Book.id.in_(
                    select(BookAuthor.book_id)
                    .join(Author, BookAuthor.author_id == Author.id)
                    .where(Author.name.ilike(f"%{author}%"))
                )
            )

        # Filter by subject (case-insensitive contains)
        if subject:
            base = base.where(
                Book.id.in_(
                    select(BookSubject.book_id).where(BookSubject.subject.ilike(f"%{subject}%"))
                )
            )

        # Filter by year range
        if year_from is not None:
            base = base.where(Book.first_publish_year >= year_from)
        if year_to is not None:
            base = base.where(Book.first_publish_year <= year_to)

        # Keyword search on title or author name
        if q:
            pattern = f"%{q}%"
            base = base.where(
                or_(
                    Book.title.ilike(pattern),
                    Book.id.in_(
                        select(BookAuthor.book_id)
                        .join(Author, BookAuthor.author_id == Author.id)
                        .where(Author.name.ilike(pattern))
                    ),
                )
            )

        # Count total
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_q)).scalar_one()

        # Fetch page with eager-loaded relations
        offset = (page - 1) * page_size
        rows_q = (
            base.options(selectinload(Book.authors), selectinload(Book.subjects))
            .order_by(Book.title)
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(rows_q)
        books = result.scalars().unique().all()

        items = [
            BookSummary(
                id=book.id,
                ol_work_key=book.ol_work_key,
                isbn=book.isbn,
                title=book.title,
                authors=[a.name for a in book.authors],
                first_publish_year=book.first_publish_year,
                cover_url=book.cover_url,
                subjects=[s.subject for s in book.subjects[:10]],
            )
            for book in books
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total > 0 else 0,
        )

    async def get_book(self, tenant_id: uuid.UUID, book_id: uuid.UUID) -> BookDetail | None:
        result = await self.session.execute(
            select(Book)
            .where(Book.tenant_id == tenant_id, Book.id == book_id)
            .options(selectinload(Book.authors), selectinload(Book.subjects))
        )
        book = result.scalar_one_or_none()
        if book is None:
            return None

        return BookDetail(
            id=book.id,
            ol_work_key=book.ol_work_key,
            isbn=book.isbn,
            title=book.title,
            authors=[
                AuthorSummary(
                    id=a.id,
                    ol_author_key=a.ol_author_key,
                    name=a.name,
                    birth_date=a.birth_date,
                )
                for a in book.authors
            ],
            first_publish_year=book.first_publish_year,
            cover_url=book.cover_url,
            description=book.description,
            subjects=[s.subject for s in book.subjects],
            created_at=book.created_at,
            updated_at=book.updated_at,
        )
