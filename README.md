# Tenant Library Catalog Service

A multi-tenant catalog service that ingests books from [Open Library](https://openlibrary.org/) and provides a REST API for searching, browsing, and managing patron reading lists. Each library tenant has fully isolated catalog data.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                             │
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │          │    │              │    │     Open Library API     │   │
│  │  Client  │───▶│   FastAPI    │───▶│  openlibrary.org/api     │   │
│  │ (curl/   │◀───│   (uvicorn)  │◀───│                          │   │
│  │  browser)│    │   :8000      │    │  - /search.json          │   │
│  │          │    │              │    │  - /works/{key}.json     │   │
│  └──────────┘    └──────┬───────┘    │  - /authors/{key}.json   │   │
│                         │            │  - /subjects/{name}.json │   │
│                         │            │  - /isbn/{isbn}.json     │   │
│                         │            └──────────────────────────┘   │
│                         │                       ▲                   │
│                         ▼                       │                   │
│                  ┌─────────────┐         ┌──────┴───────┐           │
│                  │             │         │              │           │
│                  │ PostgreSQL  │◀────────│    Celery    │           │
│                  │   :5432     │         │    Worker    │           │
│                  │             │         │              │           │
│                  │ - tenants   │         └──────────────┘           │
│                  │ - books     │                ▲                   │
│                  │ - authors   │                │                   │
│                  │ - subjects  │         ┌──────┴───────┐           │
│                  │ - jobs/logs │         │              │           │
│                  │ - reading   │         │    Redis     │           │
│                  │   lists     │         │    :6379     │           │
│                  │             │         │   (broker)   │           │
│                  └─────────────┘         └──────────────┘           │
│                                                ▲                    │
│                                         ┌──────┴───────┐            │
│                                         │  Celery Beat │            │
│                                         │  (scheduler) │            │
│                                         └──────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **Row-level tenant isolation**: All tables carry a `tenant_id` FK. A FastAPI path dependency extracts the tenant from the URL and filters every query. No data leaks between tenants.
- **Two-pass ingestion**: Search Open Library first (partial metadata), then enrich incomplete records with follow-up calls to `/works` and `/authors` endpoints.
- **Async background ingestion**: Ingestion runs in a Celery worker so API responses return immediately. A single worker process (concurrency=1) ensures we stay within Open Library's rate limit of 3 req/s.
- **HMAC-SHA256 for PII**: Patron name and email are hashed with a server secret before storage. Hashes are deterministic for deduplication but resistant to rainbow table attacks. Plaintext PII is never persisted.
- **Reading list replace semantics**: Resubmitting with the same email replaces the previous reading list items rather than appending. Unresolved books (bad work key or OL API error) are stored as-is; the patron can resubmit to retry resolution.
- **Catalog-first resolution**: When resolving books for a reading list, the service checks the local catalog before making an Open Library API call, avoiding unnecessary external requests.

## Setup & Run

### Prerequisites

- Docker and Docker Compose

### Start

```bash
make run
# or: docker compose up --build
```

This starts 5 services:
- **api** (FastAPI on port 8000) — runs Alembic migrations and seeds 3 default tenants on startup
- **db** (PostgreSQL 16)
- **redis** (Redis 7)
- **celery-worker** — processes ingestion jobs
- **celery-beat** — schedules daily catalog refresh at 3 AM UTC

### Default Tenants

| Slug | Name |
|------|------|
| `downtown-library` | Downtown Public Library |
| `westside-library` | Westside Branch Library |
| `university-library` | University Library |

### Run Tests

```bash
make test
# or: docker compose exec api pytest tests/ -v
```

### Stop

```bash
make stop
# or: docker compose down
```

## API Documentation

Interactive docs available at **http://localhost:8000/docs** when running.

All tenant-scoped endpoints are under `/api/v1/tenants/{tenant_slug}/`.

### Ingest Books

Queue a background ingestion job by author or subject:

```bash
curl -X POST http://localhost:8000/api/v1/tenants/downtown-library/ingestion \
  -H "Content-Type: application/json" \
  -d '{"query_type": "author", "query_value": "tolkien", "limit": 10}'
```

Response:
```json
{
  "job_id": "d08f6a4b-...",
  "status": "queued",
  "message": "Ingestion job queued for author 'tolkien'"
}
```

### Check Job Status

```bash
curl http://localhost:8000/api/v1/tenants/downtown-library/ingestion/jobs/{job_id}
```

Response:
```json
{
  "id": "d08f6a4b-...",
  "status": "completed",
  "progress": {"works_fetched": 10, "works_stored": 10, "works_failed": 0}
}
```

### List Books

```bash
# All books (paginated)
curl http://localhost:8000/api/v1/tenants/downtown-library/books

# Filter by author
curl "http://localhost:8000/api/v1/tenants/downtown-library/books?author=tolkien"

# Filter by subject
curl "http://localhost:8000/api/v1/tenants/downtown-library/books?subject=Fantasy"

# Filter by year range
curl "http://localhost:8000/api/v1/tenants/downtown-library/books?year_from=1950&year_to=1960"

# Keyword search (title or author)
curl "http://localhost:8000/api/v1/tenants/downtown-library/books?q=hobbit"

# Pagination
curl "http://localhost:8000/api/v1/tenants/downtown-library/books?page=1&page_size=5"
```

### Get Book Detail

```bash
curl http://localhost:8000/api/v1/tenants/downtown-library/books/{book_id}
```

### Submit Reading List

```bash
curl -X POST http://localhost:8000/api/v1/tenants/downtown-library/reading-lists \
  -H "Content-Type: application/json" \
  -d '{
    "patron_name": "Jane Smith",
    "email": "jane@example.com",
    "books": [
      {"ol_work_key": "OL27448W"},
      {"isbn": "9780618640157"},
      {"ol_work_key": "OL99999999W"}
    ]
  }'
```

Response:
```json
{
  "reading_list_id": "10337dff-...",
  "is_update": false,
  "patron_name_masked": "J*** S****",
  "email_masked": "j**e@e*****e.com",
  "resolved_books": [
    {"ol_work_key": "OL27448W", "title": "The Lord of the Rings", "found_in_catalog": true}
  ],
  "unresolved_books": [
    {"ol_work_key": "OL99999999W", "reason": "Work not found on Open Library"}
  ]
}
```

Submitting again with the same email **replaces** the previous reading list (it's an update, not append). Unresolved books can be retried by resubmitting.

### View Activity Log

```bash
curl http://localhost:8000/api/v1/tenants/downtown-library/activity-log
```

### Health Check

```bash
curl http://localhost:8000/health
```

## API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/tenants/{slug}/ingestion` | Queue ingestion job |
| `GET` | `/api/v1/tenants/{slug}/ingestion/jobs` | List ingestion jobs |
| `GET` | `/api/v1/tenants/{slug}/ingestion/jobs/{id}` | Job status & progress |
| `GET` | `/api/v1/tenants/{slug}/books` | List/filter/search books |
| `GET` | `/api/v1/tenants/{slug}/books/{id}` | Book detail |
| `POST` | `/api/v1/tenants/{slug}/reading-lists` | Submit reading list |
| `GET` | `/api/v1/tenants/{slug}/reading-lists` | List reading lists |
| `GET` | `/api/v1/tenants/{slug}/reading-lists/{id}` | Reading list detail |
| `GET` | `/api/v1/tenants/{slug}/activity-log` | Ingestion history |

## Tech Stack

- **Python 3.12** / **FastAPI** / **uvicorn**
- **PostgreSQL 16** / **SQLAlchemy 2.0** (async) / **Alembic**
- **Celery** + **Redis** (background jobs & scheduling)
- **httpx** (async HTTP client for Open Library)
- **Docker Compose** (orchestration)

## What I'd Do Differently With More Time

- **Tier 3 — Version management**: Track metadata changes across re-ingestions with a version history table and diff API
- **Tier 3 — Noisy neighbor throttling**: Per-tenant rate limiting with Redis token buckets and resource consumption dashboards
- **Full-text search**: PostgreSQL `tsvector` GIN index on book titles for faster keyword search at scale
- **Separate test database**: Tests currently run against the main DB; a dedicated test DB would prevent interference
- **OpenAPI client mock**: Use `respx` to mock the OL client in tests for faster, more reliable test runs
- **Pagination cursors**: Cursor-based pagination instead of offset/limit for better performance on large datasets
- **Observability**: Structured logging, Prometheus metrics, and request tracing
