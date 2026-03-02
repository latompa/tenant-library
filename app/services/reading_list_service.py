"""Reading list submission with PII hashing and book resolution."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openlibrary import OpenLibraryClient, OpenLibraryError
from app.models.book import Book
from app.models.reading_list import ReadingList, ReadingListItem
from app.schemas.reading_list import (
    BookReference,
    ReadingListResponse,
    ReadingListSubmission,
    ResolvedBook,
    UnresolvedBook,
)
from app.services.pii import hash_pii, mask_email, mask_name

logger = logging.getLogger(__name__)


class ReadingListService:
    def __init__(self, session: AsyncSession, ol_client: OpenLibraryClient):
        self.session = session
        self.ol_client = ol_client

    async def submit(
        self, tenant_id: uuid.UUID, submission: ReadingListSubmission
    ) -> ReadingListResponse:
        """Process a reading list submission: hash PII, resolve books, persist."""
        email_hash = hash_pii(submission.email)
        name_hash = hash_pii(submission.patron_name)
        email_masked = mask_email(submission.email)
        name_masked = mask_name(submission.patron_name)

        # Check for existing reading list (dedup by email)
        result = await self.session.execute(
            select(ReadingList).where(
                ReadingList.tenant_id == tenant_id,
                ReadingList.email_hash == email_hash,
            )
        )
        reading_list = result.scalar_one_or_none()
        is_update = reading_list is not None

        if reading_list is None:
            reading_list = ReadingList(
                tenant_id=tenant_id,
                patron_name_hash=name_hash,
                email_hash=email_hash,
                patron_name_masked=name_masked,
                email_masked=email_masked,
            )
            self.session.add(reading_list)
            await self.session.flush()
        else:
            # Update name in case it changed
            reading_list.patron_name_hash = name_hash
            reading_list.patron_name_masked = name_masked
            # Replace: clear old items so the new submission is the current list
            from sqlalchemy import delete
            await self.session.execute(
                delete(ReadingListItem).where(
                    ReadingListItem.reading_list_id == reading_list.id
                )
            )
            await self.session.flush()

        # Resolve each book reference
        resolved_books: list[ResolvedBook] = []
        unresolved_books: list[UnresolvedBook] = []

        for book_ref in submission.books:
            resolved, unresolved = await self._resolve_book(tenant_id, book_ref)
            if resolved:
                resolved_books.append(resolved)
                # Add item to reading list
                book_id = None
                if resolved.found_in_catalog:
                    catalog_book = await self._find_by_work_key(tenant_id, resolved.ol_work_key)
                    if catalog_book:
                        book_id = catalog_book.id
                item = ReadingListItem(
                    reading_list_id=reading_list.id,
                    ol_work_key=resolved.ol_work_key,
                    isbn=book_ref.isbn,
                    book_id=book_id,
                    resolved=True,
                )
                self.session.add(item)
            else:
                unresolved_books.append(unresolved)
                # Still add the item as unresolved
                self.session.add(ReadingListItem(
                    reading_list_id=reading_list.id,
                    ol_work_key=book_ref.ol_work_key,
                    isbn=book_ref.isbn,
                    resolved=False,
                ))

        await self.session.commit()

        return ReadingListResponse(
            reading_list_id=reading_list.id,
            is_update=is_update,
            patron_name_masked=name_masked,
            email_masked=email_masked,
            resolved_books=resolved_books,
            unresolved_books=unresolved_books,
        )

    async def _resolve_book(
        self, tenant_id: uuid.UUID, book_ref: BookReference
    ) -> tuple[ResolvedBook | None, UnresolvedBook | None]:
        """Try to resolve a book reference. Checks ISBN first, then OL work key."""
        work_key = book_ref.ol_work_key

        # If ISBN provided, try catalog ISBN lookup first
        if book_ref.isbn:
            catalog_book = await self._find_by_isbn(tenant_id, book_ref.isbn)
            if catalog_book:
                return ResolvedBook(
                    ol_work_key=catalog_book.ol_work_key,
                    title=catalog_book.title,
                    found_in_catalog=True,
                ), None

            # ISBN not in catalog — resolve to work key via OL
            if not work_key:
                try:
                    work_key = await self.ol_client.resolve_isbn(book_ref.isbn)
                except OpenLibraryError:
                    pass
                if not work_key:
                    return None, UnresolvedBook(
                        isbn=book_ref.isbn, reason="ISBN not found on Open Library"
                    )

        # Check catalog by work key
        if work_key:
            catalog_book = await self._find_by_work_key(tenant_id, work_key)
            if catalog_book:
                return ResolvedBook(
                    ol_work_key=work_key,
                    title=catalog_book.title,
                    found_in_catalog=True,
                ), None

        # Not in catalog — verify it exists on Open Library
        try:
            work_detail = await self.ol_client.get_work(work_key)
        except OpenLibraryError:
            return None, UnresolvedBook(
                ol_work_key=work_key, isbn=book_ref.isbn,
                reason="Work not found on Open Library",
            )

        return ResolvedBook(
            ol_work_key=work_key,
            title=work_detail.title,
            found_in_catalog=False,
        ), None

    async def _find_by_isbn(self, tenant_id: uuid.UUID, isbn: str) -> Book | None:
        result = await self.session.execute(
            select(Book).where(
                Book.tenant_id == tenant_id, Book.isbn == isbn
            )
        )
        return result.scalar_one_or_none()

    async def _find_by_work_key(self, tenant_id: uuid.UUID, ol_work_key: str) -> Book | None:
        result = await self.session.execute(
            select(Book).where(
                Book.tenant_id == tenant_id, Book.ol_work_key == ol_work_key
            )
        )
        return result.scalar_one_or_none()
