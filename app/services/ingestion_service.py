"""Two-pass ingestion pipeline: search Open Library, then enrich incomplete records."""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.openlibrary import OpenLibraryClient, OpenLibraryError, SearchResult
from app.models.author import Author
from app.models.book import Book, BookAuthor, BookSubject
from app.models.ingestion import IngestionLog

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(self, session: AsyncSession, ol_client: OpenLibraryClient):
        self.session = session
        self.ol_client = ol_client

    async def ingest(
        self, tenant_id: uuid.UUID, query_type: str, query_value: str, limit: int = 50
    ) -> IngestionLog:
        """Run the full ingestion pipeline and return the activity log entry."""
        log = IngestionLog(
            tenant_id=tenant_id,
            query_type=query_type,
            query_value=query_value,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(log)
        await self.session.flush()

        try:
            # Pass 1: Search
            if query_type == "author":
                search_results = await self.ol_client.search_by_author(query_value, limit=limit)
            else:
                search_results = await self.ol_client.search_by_subject(query_value, limit=limit)

            log.works_fetched = len(search_results)

            # Pass 2: Enrich and store each work
            stored = 0
            failed = 0
            for result in search_results:
                try:
                    await self._enrich_and_store(tenant_id, result)
                    stored += 1
                except Exception:
                    logger.exception(f"Failed to store work {result.work_key}")
                    failed += 1

            log.works_stored = stored
            log.works_failed = failed
            log.status = "completed"
            log.completed_at = datetime.now(timezone.utc)

        except Exception as exc:
            logger.exception("Ingestion pipeline failed")
            log.status = "failed"
            log.error_message = str(exc)[:2000]
            log.completed_at = datetime.now(timezone.utc)

        await self.session.commit()
        return log

    async def _enrich_and_store(self, tenant_id: uuid.UUID, result: SearchResult) -> None:
        """Enrich a search result with follow-up API calls if needed, then upsert into DB."""
        title = result.title
        author_names = list(result.author_names)
        author_keys = list(result.author_keys)
        subjects = list(result.subjects)
        cover_id = result.cover_id
        first_publish_year = result.first_publish_year
        description = None

        # Enrich if critical fields are missing
        needs_enrichment = not subjects or not author_names or cover_id is None
        if needs_enrichment:
            try:
                work_detail = await self.ol_client.get_work(result.work_key)
                title = title or work_detail.title
                subjects = subjects or work_detail.subjects
                description = work_detail.description
                if cover_id is None and work_detail.cover_ids:
                    cover_id = work_detail.cover_ids[0]

                # Resolve author names from work detail if still missing
                if not author_names and work_detail.author_refs:
                    author_keys = work_detail.author_refs
                    for key in work_detail.author_refs:
                        try:
                            author_detail = await self.ol_client.get_author(key)
                            author_names.append(author_detail.name)
                        except OpenLibraryError:
                            logger.warning(f"Could not resolve author {key}")
            except OpenLibraryError:
                logger.warning(f"Could not enrich work {result.work_key}, storing with partial data")

        # Build cover URL
        cover_url = self.ol_client.build_cover_url(cover_id) if cover_id else None

        # Upsert book
        existing_book = await self.session.execute(
            select(Book).where(Book.tenant_id == tenant_id, Book.ol_work_key == result.work_key)
        )
        book = existing_book.scalar_one_or_none()

        if book is None:
            book = Book(
                tenant_id=tenant_id,
                ol_work_key=result.work_key,
                title=title,
                first_publish_year=first_publish_year,
                cover_id=cover_id,
                cover_url=cover_url,
                description=description,
            )
            self.session.add(book)
            await self.session.flush()
        else:
            # Update existing book
            book.title = title
            book.first_publish_year = first_publish_year or book.first_publish_year
            book.cover_id = cover_id or book.cover_id
            book.cover_url = cover_url or book.cover_url
            book.description = description or book.description

        # Upsert authors and link to book
        for i, author_name in enumerate(author_names):
            author_key = author_keys[i] if i < len(author_keys) else f"unknown-{uuid.uuid4().hex[:8]}"
            author = await self._upsert_author(tenant_id, author_key, author_name)

            # Check if link already exists
            existing_link = await self.session.execute(
                select(BookAuthor).where(
                    BookAuthor.book_id == book.id, BookAuthor.author_id == author.id
                )
            )
            if existing_link.scalar_one_or_none() is None:
                self.session.add(BookAuthor(book_id=book.id, author_id=author.id))

        # Upsert subjects
        for subject_name in subjects[:50]:  # cap at 50 subjects per book
            existing_subj = await self.session.execute(
                select(BookSubject).where(
                    BookSubject.book_id == book.id, BookSubject.subject == subject_name
                )
            )
            if existing_subj.scalar_one_or_none() is None:
                self.session.add(BookSubject(book_id=book.id, subject=subject_name))

        await self.session.flush()

    async def _upsert_author(
        self, tenant_id: uuid.UUID, ol_author_key: str, name: str
    ) -> Author:
        """Find or create an author."""
        result = await self.session.execute(
            select(Author).where(
                Author.tenant_id == tenant_id, Author.ol_author_key == ol_author_key
            )
        )
        author = result.scalar_one_or_none()
        if author is None:
            author = Author(tenant_id=tenant_id, ol_author_key=ol_author_key, name=name)
            self.session.add(author)
            await self.session.flush()
        return author
