# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-tenant catalog service in Python that ingests books from the [Open Library API](https://openlibrary.org/developers/api) and provides a local REST API for searching, browsing, and managing reading list submissions. Each library tenant has isolated catalog data and patron reading lists.

See `assignment.txt` for the full specification and tiered requirements.

## Key Constraints

- **Live API only**: Must call the real Open Library API — no hard-coded/cached sample responses as test fixtures.
- **PII handling**: Patron name and email must be irreversibly hashed before storage. Hashed email is used for deduplication.
- **Tenant isolation**: All API operations are scoped to a tenant via URL path (`/api/v1/tenants/{tenant_slug}/...`). One tenant's data must never appear in another's responses.
- **Single-command startup**: The project must be runnable via `make run`, `docker compose up`, or equivalent.
- **Prompt log required**: All AI interactions must be captured in `prompt-log.md` at repo root.

## Build & Run

```bash
make run          # docker compose up --build
make stop         # docker compose down
make test         # docker compose exec api pytest tests/ -v
```

Run a single test file:
```bash
docker compose exec api pytest tests/test_services/test_pii.py -v
```

Run a single test by name:
```bash
docker compose exec api pytest tests/ -v -k test_submit_reading_list
```

## Tech Stack

- **Python 3.12** / **FastAPI** / **uvicorn** (API server)
- **PostgreSQL 16** / **SQLAlchemy 2.0** async / **Alembic** (database + migrations)
- **Celery** + **Redis** (background ingestion jobs + daily refresh via Beat)
- **httpx** (async HTTP client for Open Library)
- **Docker Compose** (5 services: api, db, redis, celery-worker, celery-beat)

## Architecture

- **Row-level tenant isolation**: Every table carries `tenant_id` FK. FastAPI path dependency (`app/api/deps.py`) extracts tenant from URL and filters queries.
- **Two-pass ingestion**: Search OL first (partial data), then enrich via `/works` and `/authors` endpoints (`app/services/ingestion_service.py`).
- **Async background ingestion**: Celery worker with concurrency=1 to stay within OL's 3 req/s rate limit. Tasks in `app/tasks/ingestion_tasks.py`.
- **HMAC-SHA256 PII hashing**: Patron name/email hashed with server secret (`app/services/pii.py`). Email hash used for dedup. Plaintext never stored.
- **Reading list replace semantics**: Resubmitting with the same email replaces previous items, not appends (`app/services/reading_list_service.py`).
- **Catalog-first resolution**: Reading list book resolution checks local catalog before hitting OL API.

## Key Directories

- `app/api/v1/` — Route handlers (books, ingestion, reading_lists, activity_log)
- `app/services/` — Business logic (ingestion pipeline, book queries, reading lists, PII)
- `app/clients/openlibrary.py` — OL API client with rate limiting, retries, backoff
- `app/models/` — SQLAlchemy models (9 tables)
- `app/tasks/` — Celery app, ingestion tasks, Beat schedule
- `tests/` — pytest suite (unit + integration, 34 tests)
