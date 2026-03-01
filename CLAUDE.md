# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-tenant catalog service in Python that ingests books from the [Open Library API](https://openlibrary.org/developers/api) and provides a local REST API for searching, browsing, and managing reading list submissions. Each library tenant has isolated catalog data and patron reading lists.

See `assignment.txt` for the full specification and tiered requirements.

## Key Constraints

- **Live API only**: Must call the real Open Library API — no hard-coded/cached sample responses as test fixtures.
- **PII handling**: Patron name and email must be irreversibly hashed before storage. Hashed email is used for deduplication.
- **Tenant isolation**: All API operations are scoped to a tenant. One tenant's data must never appear in another's responses.
- **Single-command startup**: The project must be runnable via `make run`, `docker compose up`, or equivalent.
- **Prompt log required**: All AI interactions must be captured in `prompt-log.md` at repo root.

## Architecture (Planned Tiers)

**Tier 1 — Core**: Ingest works by author/subject from Open Library, store locally with full metadata (title, authors, year, subjects, cover URL). REST API for listing, filtering, searching, and detail views. Activity log for ingestion operations.

**Tier 2 — Production**: Reading list submissions with PII hashing. Background job queue for non-blocking ingestion with progress visibility and automatic catalog freshness.

**Tier 3 — Depth options**: Version management (track metadata changes across re-ingestions) or noisy neighbor throttling (per-tenant resource limits).
