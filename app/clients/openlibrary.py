"""Open Library API client with rate limiting, retries, and data normalization."""

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# --- Data classes (pure data, not SQLAlchemy models) ---


@dataclass
class SearchResult:
    work_key: str  # e.g. "OL27448W"
    title: str
    author_names: list[str] = field(default_factory=list)
    author_keys: list[str] = field(default_factory=list)
    first_publish_year: int | None = None
    cover_id: int | None = None
    subjects: list[str] = field(default_factory=list)
    isbn: str | None = None  # first ISBN if available


@dataclass
class WorkDetail:
    work_key: str
    title: str
    author_refs: list[str] = field(default_factory=list)  # e.g. ["OL26320A"]
    first_publish_date: str | None = None
    cover_ids: list[int] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    description: str | None = None


@dataclass
class AuthorDetail:
    author_key: str  # e.g. "OL26320A"
    name: str
    birth_date: str | None = None
    death_date: str | None = None
    bio: str | None = None
    photo_ids: list[int] = field(default_factory=list)


class OpenLibraryError(Exception):
    """Raised when an Open Library API call fails after retries."""

    pass


class OpenLibraryClient:
    BASE_URL = "https://openlibrary.org"
    COVERS_URL = "https://covers.openlibrary.org"
    USER_AGENT = "TenantLibraryCatalog/1.0 (tenant-library-project)"
    MAX_RETRIES = 3

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(
            headers={"User-Agent": self.USER_AGENT},
            timeout=settings.OL_REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        self._owns_client = http_client is None
        self._semaphore = asyncio.Semaphore(1)
        self._last_request_time: float = 0.0
        self._rate_limit_interval = 1.0 / settings.OL_RATE_LIMIT_RPS

    async def close(self):
        if self._owns_client:
            await self._client.aclose()

    async def _rate_limited_get(self, url: str, params: dict | None = None) -> httpx.Response:
        """GET with rate limiting, retries, and backoff."""
        async with self._semaphore:
            for attempt in range(self.MAX_RETRIES):
                # Enforce rate limit
                elapsed = time.monotonic() - self._last_request_time
                if elapsed < self._rate_limit_interval:
                    await asyncio.sleep(self._rate_limit_interval - elapsed)

                try:
                    self._last_request_time = time.monotonic()
                    response = await self._client.get(url, params=params)

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 5))
                        logger.warning(f"Rate limited (429), waiting {retry_after}s (attempt {attempt + 1})")
                        await asyncio.sleep(retry_after)
                        continue

                    response.raise_for_status()
                    return response

                except httpx.TimeoutException:
                    logger.warning(f"Timeout on {url} (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    if attempt == self.MAX_RETRIES - 1:
                        raise OpenLibraryError(f"Timeout after {self.MAX_RETRIES} retries: {url}")
                    await asyncio.sleep(2**attempt)

                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                        logger.warning(f"Server error {exc.response.status_code} on {url} (attempt {attempt + 1})")
                        await asyncio.sleep(2**attempt)
                        continue
                    raise OpenLibraryError(
                        f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:200]}"
                    )

        raise OpenLibraryError(f"Failed after {self.MAX_RETRIES} retries: {url}")

    @staticmethod
    def _extract_text(value) -> str | None:
        """OL fields can be a plain string or {"type": "/type/text", "value": "..."}."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("value")
        return None

    @staticmethod
    def _strip_key(path: str) -> str:
        """'/works/OL27448W' -> 'OL27448W', '/authors/OL26320A' -> 'OL26320A'."""
        return path.rsplit("/", 1)[-1]

    # --- Public API methods ---

    async def search_by_author(self, author_name: str, limit: int = 50) -> list[SearchResult]:
        """Search works by author name."""
        response = await self._rate_limited_get(
            f"{self.BASE_URL}/search.json",
            params={
                "author": author_name,
                "limit": limit,
                "fields": "key,title,author_name,author_key,first_publish_year,subject,cover_i,isbn",
            },
        )
        data = response.json()
        results = []
        for doc in data.get("docs", []):
            key = doc.get("key", "")
            isbns = doc.get("isbn", [])
            results.append(
                SearchResult(
                    work_key=self._strip_key(key),
                    title=doc.get("title", "Unknown"),
                    author_names=doc.get("author_name", []),
                    author_keys=[self._strip_key(k) for k in doc.get("author_key", [])],
                    first_publish_year=doc.get("first_publish_year"),
                    cover_id=doc.get("cover_i"),
                    subjects=doc.get("subject", [])[:50],  # cap subjects
                    isbn=isbns[0] if isbns else None,
                )
            )
        return results

    async def search_by_subject(self, subject: str, limit: int = 50) -> list[SearchResult]:
        """Fetch works for a subject."""
        normalized = subject.lower().replace(" ", "_")
        response = await self._rate_limited_get(
            f"{self.BASE_URL}/subjects/{normalized}.json",
            params={"limit": limit},
        )
        data = response.json()
        results = []
        for work in data.get("works", []):
            key = work.get("key", "")
            # Subjects endpoint provides authors inline
            authors = work.get("authors", [])
            author_names = [a.get("name", "") for a in authors if a.get("name")]
            author_keys = [self._strip_key(a.get("key", "")) for a in authors if a.get("key")]
            results.append(
                SearchResult(
                    work_key=self._strip_key(key),
                    title=work.get("title", "Unknown"),
                    author_names=author_names,
                    author_keys=author_keys,
                    first_publish_year=work.get("first_publish_year"),
                    cover_id=work.get("cover_id"),
                    subjects=work.get("subject", [])[:50],
                )
            )
        return results

    async def get_work(self, work_key: str) -> WorkDetail:
        """Get full work details for enrichment."""
        response = await self._rate_limited_get(f"{self.BASE_URL}/works/{work_key}.json")
        data = response.json()

        author_refs = []
        for author_entry in data.get("authors", []):
            author_obj = author_entry.get("author", {})
            key = author_obj.get("key", "")
            if key:
                author_refs.append(self._strip_key(key))

        return WorkDetail(
            work_key=work_key,
            title=data.get("title", "Unknown"),
            author_refs=author_refs,
            first_publish_date=data.get("first_publish_date"),
            cover_ids=data.get("covers", []),
            subjects=data.get("subjects", [])[:50],
            description=self._extract_text(data.get("description")),
        )

    async def get_author(self, author_key: str) -> AuthorDetail:
        """Resolve author metadata from author key."""
        response = await self._rate_limited_get(f"{self.BASE_URL}/authors/{author_key}.json")
        data = response.json()
        return AuthorDetail(
            author_key=author_key,
            name=data.get("name", "Unknown"),
            birth_date=data.get("birth_date"),
            death_date=data.get("death_date"),
            bio=self._extract_text(data.get("bio")),
            photo_ids=data.get("photos", []),
        )

    async def resolve_isbn(self, isbn: str) -> str | None:
        """Convert ISBN to Open Library work key. Returns None if not found."""
        try:
            response = await self._rate_limited_get(f"{self.BASE_URL}/isbn/{isbn}.json")
            data = response.json()
            works = data.get("works", [])
            if works:
                return self._strip_key(works[0].get("key", ""))
            return None
        except OpenLibraryError:
            return None

    @staticmethod
    def build_cover_url(cover_id: int, size: str = "M") -> str:
        """Build cover image URL from cover ID."""
        return f"https://covers.openlibrary.org/b/id/{cover_id}-{size}.jpg"
