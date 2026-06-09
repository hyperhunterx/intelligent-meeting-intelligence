# Build Progress — IMIES

Status: **COMPLETE** ✅ — all core requirements + 5 bonus features built, tested, and verified live.

| Task | Description | Status |
|---|---|---|
| 0 | Scaffold (deps, config, env, gitignore) | ✅ done |
| 1 | Database models (SQLAlchemy knowledge graph) | ✅ done |
| 2 | Pydantic schemas (extraction contract) | ✅ done |
| 3 | enrich.py — pure logic (TDD, 8 tests) | ✅ done |
| 4 | LLM client (OpenRouter) | ✅ done |
| 5 | Ingestion pipeline | ✅ done |
| 6 | Insights + NL query (TDD, 5 tests) | ✅ done |
| 7 | Reports + graph | ✅ done |
| 8 | FastAPI app + routes | ✅ done |
| 9 | Dashboard (SPA) | ✅ done |
| 10 | Seed data + README | ✅ done |
| 11 | End-to-end verification | ✅ done |

## Verification evidence
- `pytest` → **13/13 passing** (entity resolution, severity scoring, duplicate detection, insights aggregation).
- `python seed.py --reset` → 5 meetings ingested through the real LLM pipeline.
- Entity resolution confirmed: "Rahul" is one node, workload = 2 tasks across 2 meetings.
- Duplicate detection confirmed: 2nd Vendor API escalation flagged `[DUPLICATE]`.
- Severity scoring confirmed: 85 (high) / 60 (medium).
- All 5 PDF example NL queries return correct grounded answers with cited sources.
- Report endpoint generates a structured leadership Markdown report.
- Dashboard verified in-browser (screenshots: `dashboard-escalations.png`, `-insights.png`, `-graph.png`):
  KPIs, escalation severity bars + duplicate badge, insights charts, relationship graph.

## Key fixes during build
- **Model id:** `.env` default `google/gemini-2.0-flash-001` → 404 on this OpenRouter account.
  Switched to verified `google/gemini-2.5-flash`. (Model is swappable in one line.)
- **NL query retrieval bug:** keyword matching couldn't find escalations for "unresolved
  escalations" (the word "escalation" isn't in an escalation's text). Rewrote retrieval to be
  TYPE-AWARE (understands entity-type + open/unresolved status words) and added blocker retrieval.

## Known limitations (future work)
- Entity resolution is exact-normalized-name; the model occasionally names a project two ways
  ("Phase-2" vs "Phase-2 release") creating two nodes. Fuzzy/embedding-based resolution would fix it.
- Deferred bonuses: multi-agent orchestration, vector/semantic search, Slack/Teams, voice ingestion.

## Stack
FastAPI · SQLite/SQLAlchemy · OpenRouter (model swappable via `.env`) · Pydantic · vanilla SPA.
LLM used twice: EXTRACT on ingest, ANSWER on query. Everything between is deterministic SQL.
