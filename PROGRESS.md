# Build Progress — IMIES

Live status of the build. Updated as tasks complete.

| Task | Description | Status |
|---|---|---|
| 0 | Scaffold (deps, config, env, gitignore) | ✅ done |
| 1 | Database models (SQLAlchemy) | ⏳ in progress |
| 2 | Pydantic schemas (extraction contract) | ⬜ todo |
| 3 | enrich.py — pure logic (TDD) | ⬜ todo |
| 4 | LLM client (OpenRouter) | ⬜ todo |
| 5 | Ingestion pipeline | ⬜ todo |
| 6 | Insights + NL query (TDD on insights) | ⬜ todo |
| 7 | Reports + graph | ⬜ todo |
| 8 | FastAPI app + routes | ⬜ todo |
| 9 | Dashboard (SPA) | ⬜ todo |
| 10 | Seed data + README | ⬜ todo |
| 11 | End-to-end verification | ⬜ todo |

## Notes
- Stack: FastAPI · SQLite/SQLAlchemy · OpenRouter (model swappable via `.env`) · vanilla SPA.
- LLM used twice: EXTRACT on ingest, ANSWER on query. Everything between is deterministic SQL.
