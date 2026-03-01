# Multi-Tenant Library Catalog Service — Implementation Plan

## Context

Building the project described in `assignment.txt`: a multi-tenant catalog service that ingests books from Open Library and provides a REST API for searching, browsing, and managing reading lists. Targeting Tier 1 + Tier 2 (skipping Tier 3).

## Assignment Gaps & Decisions Made

The assignment leaves several things unspecified. Here's what was unclear and the decisions made:

| Gap in Assignment | Decision |
|---|---|
| No framework specified | **FastAPI** (async, auto OpenAPI docs) |
| No database specified ("store locally") | **PostgreSQL via Docker** |
| No job queue technology specified | **Celery + Redis** |
| Tier 3 scope | **Skip** — focus on solid Tier 1 + 2 |
| Tenant identification mechanism unspecified | **`X-Tenant-ID` header** on every request |
| Tenant isolation strategy unspecified | **Row-level isolation** — shared DB, `tenant_id` FK on every table |
| How to handle OL rate limits (1 req/s unauthenticated, 3 req/s with User-Agent) | **Set User-Agent header** for 3 req/s, semaphore-based rate limiter in client |
| "Catalog should stay fresh" — no specifics | **Celery Beat periodic task** re-runs recent ingestion queries daily |
| PII hashing method unspecified | **HMAC-SHA256** with server-side secret (prevents rainbow tables) |

### Additional Notes from API Exploration

- Open Library search endpoint returns partial data — many works lack subjects, descriptions, or cover IDs. The ingestion service needs a **two-pass approach**: search first, then enrich incomplete records via `/works/{key}.json` and `/authors/{key}.json`.
- The subjects API (`/subjects/{name}.json`) and search API (`/search.json`) return differently shaped responses — the client must normalize both.
- Cover URLs follow a stable pattern: `https://covers.openlibrary.org/b/id/{cover_id}-M.jpg`

## Tech Stack

- **FastAPI** + **uvicorn** (API server)
- **PostgreSQL 16** (database) + **SQLAlchemy 2.0** async + **Alembic** (migrations)
- **Celery** + **Redis** (background jobs + periodic refresh)
- **httpx** (async HTTP client for Open Library)
- **Docker Compose** (single-command startup)
- **pydantic-settings** (config from env vars)

## Project Structure

```
tenant-library/
├── docker-compose.yml
├── Dockerfile
├── Makefile                        # run, test, migrate targets
├── requirements.txt
├── README.md
├── prompt-log.md
├── alembic.ini
├── alembic/versions/
├── app/
│   ├── main.py                     # FastAPI app, lifespan, middleware
│   ├── config.py                   # Settings from env vars
│   ├── database.py                 # async engine + session factory
│   ├── models/                     # SQLAlchemy models (tenant, book, author, etc.)
│   ├── schemas/                    # Pydantic request/response schemas
│   ├── api/
│   │   ├── deps.py                 # Tenant extraction dependency
│   │   └── v1/                     # Versioned route modules
│   │       ├── books.py
│   │       ├── ingestion.py
│   │       ├── activity_log.py
│   │       └── reading_lists.py
│   ├── services/                   # Business logic
│   │   ├── book_service.py
│   │   ├── ingestion_service.py
│   │   ├── reading_list_service.py
│   │   └── pii.py                  # HMAC hashing + masking
│   ├── clients/
│   │   └── openlibrary.py          # OL API client w/ rate limiting + retries
│   └── tasks/
│       ├── celery_app.py
│       ├── ingestion_tasks.py
│       └── periodic.py             # Celery Beat schedule
└── tests/
```

## Database Schema (Key Tables)

- **tenants** — `id` (UUID), `name`, `slug` (used in X-Tenant-ID header)
- **books** — `id`, `tenant_id` FK, `ol_work_key` (unique per tenant), `title`, `first_publish_year`, `cover_url`, `description`
- **authors** — `id`, `tenant_id` FK, `ol_author_key` (unique per tenant), `name`, `birth_date`
- **book_authors** — many-to-many join table
- **book_subjects** — `book_id` FK, `subject` (string, unique per book)
- **ingestion_jobs** — tracks Celery task lifecycle: queued → running → completed/failed, with progress JSONB
- **ingestion_logs** — historical record: query type/value, works fetched/stored/failed, timestamps, errors
- **reading_lists** — `tenant_id` FK, `patron_name_hash`, `email_hash`, masked versions. Unique on `(tenant_id, email_hash)` for dedup
- **reading_list_items** — `reading_list_id` FK, `ol_work_key`, `isbn`, `book_id` FK (nullable), `resolved` bool

## API Endpoints

All require `X-Tenant-ID` header. All under `/api/v1/`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/books` | List books (paginated, filterable by author/subject/year, keyword search via `?q=`) |
| `GET` | `/books/{id}` | Single book detail |
| `POST` | `/ingestion` | Queue ingestion job (author or subject) — returns job_id |
| `GET` | `/ingestion/jobs` | List ingestion jobs |
| `GET` | `/ingestion/jobs/{id}` | Job status + progress |
| `GET` | `/activity-log` | Paginated ingestion history |
| `POST` | `/reading-lists` | Submit reading list (PII hashed before storage) |
| `GET` | `/reading-lists` | List reading lists (masked PII) |
| `GET` | `/reading-lists/{id}` | Reading list detail |

## Key Design Decisions

1. **Two-pass ingestion**: Search OL first (partial data), then enrich incomplete records with `/works/{key}.json` + `/authors/{key}.json` follow-ups
2. **HMAC-SHA256 for PII** with a `PII_HASH_SECRET` env var — deterministic for dedup, resistant to rainbow tables
3. **Celery with `asyncio.run()`** inside tasks — keeps all DB/HTTP code async, bridges into Celery's sync worker
4. **Worker concurrency of 2** — stays within OL's 3 req/s limit with interleaved requests
5. **Subjects stored as rows** (not normalized table) — OL subjects are free-text with no canonical IDs

## Implementation Order

### Phase 1: Skeleton + Database
- `docker-compose.yml`, `Dockerfile`, `Makefile`, `requirements.txt`
- `app/config.py`, `app/database.py`, `app/main.py`
- All SQLAlchemy models + Alembic initial migration
- Seed script with 2-3 default tenants
- **Verify**: `docker compose up` starts everything, tables created

### Phase 2: Open Library Client
- `app/clients/openlibrary.py` — all methods, rate limiting, retries, data normalization
- **Verify**: Call `search_by_author("tolkien")` from REPL, results returned

### Phase 3: Ingestion (sync first)
- `app/services/ingestion_service.py` — two-pass pipeline
- `app/api/deps.py` — tenant dependency
- `app/api/v1/ingestion.py` + `activity_log.py`
- **Verify**: `POST /api/v1/ingestion` fetches and stores works, activity log populated

### Phase 4: Book Retrieval API
- `app/services/book_service.py` + `app/api/v1/books.py`
- Pagination, filtering, keyword search, detail endpoint
- **Verify**: All query combinations return correct results

### Phase 5: Async Ingestion (Celery)
- `app/tasks/` — Celery app, ingestion tasks, periodic refresh
- Refactor ingestion endpoint to queue tasks instead of blocking
- Job status + progress tracking
- **Verify**: POST returns immediately, worker processes in background, job status updates

### Phase 6: PII + Reading Lists
- `app/services/pii.py` + `app/services/reading_list_service.py`
- `app/api/v1/reading_lists.py`
- **Verify**: Submissions hashed/masked, dedup works, book resolution reported

### Phase 7: Polish
- Tests (unit + integration)
- `README.md` with architecture, setup, curl examples
- `prompt-log.md`
- **Verify**: `pytest` passes, `docker compose up` works from scratch

## Docker Compose Services

5 services: **db** (postgres:16), **redis** (redis:7), **api** (FastAPI + uvicorn), **celery-worker**, **celery-beat**. Health checks on db and redis, api/workers depend on both being healthy.

## Verification

1. `docker compose up` — all 5 services start, migrations run, seed tenants created
2. `POST /api/v1/ingestion` with `X-Tenant-ID: library-a` — job queued, worker ingests books
3. `GET /api/v1/books` — paginated results with filters working
4. `POST /api/v1/reading-lists` — PII masked in response and DB, dedup on repeat
5. `GET /api/v1/activity-log` — shows ingestion history
6. Same ingestion with `X-Tenant-ID: library-b` — data isolated between tenants
7. `pytest` — all tests pass
