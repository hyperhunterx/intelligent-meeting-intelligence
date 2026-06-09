# IMIES — Intelligent Meeting Intelligence & Escalation Tracking System

Turns raw, unstructured meeting content (summaries, transcripts, chat threads, uploaded
files) into **structured, queryable, interconnected organizational intelligence** —
tracking escalations, tasks, owners, risks, projects, and operational health across an
organization, using Generative AI.

> GenAI Hackathon submission. Built with FastAPI · SQLite · OpenRouter (any LLM, swappable).

---

## What it does

1. **Ingest** a meeting → an LLM extracts projects, action items, owners, deadlines,
   escalations, risks, blockers, decisions, sentiment, and urgency into a strict schema.
2. **Structure & interconnect** it in a SQLite "knowledge graph" — the same person or
   project across many meetings becomes one linked node (cross-meeting accountability).
3. **Enrich** it: numeric **risk-severity scoring**, **duplicate-escalation detection**
   across meetings, and sentiment/urgency tagging.
4. **Query** it in plain English — answers are grounded in the database and cite the
   meetings they came from.
5. **Surface** org-wide insight: escalation trends, project health, workload distribution,
   accountability gaps, and a cross-team dependency/relationship graph — on a live
   leadership dashboard, plus an auto-generated action report.

---

## Architecture

```
Raw meeting text ──► [LLM extraction] ──► structured JSON (Pydantic-validated)
        │                                      │
        │                          [enrich: dedupe people/projects, score
        │                           severity, flag duplicate escalations]
        ▼                                      ▼
   POST /api/ingest ───────────────► SQLite (the organization's memory)
                                              │
   POST /api/query   GET /api/insights   GET /api/graph   POST /api/report   Dashboard
   (English, grounded) (deterministic SQL) (relationships) (LLM report)      (SPA)
```

**Key design choice:** the LLM is used *twice* — to **extract** structure on ingest, and
to **answer** English questions over already-structured data. Everything between is
deterministic SQL, so the AI never invents your data; it reads from a real database. That
makes the system reliable and explainable.

### Code map
| File | Responsibility |
|---|---|
| `app/config.py` | Settings from `.env` (API key, model, DB path) |
| `app/db.py` / `app/models.py` | SQLAlchemy engine + the knowledge-graph tables |
| `app/schemas.py` | Pydantic extraction contract + API I/O |
| `app/enrich.py` | Pure logic: entity normalization, severity scoring, duplicate detection (unit-tested) |
| `app/llm.py` | OpenRouter client: `extract_meeting`, `answer_query`, `generate_report` |
| `app/extraction.py` | Ingestion pipeline: extract → enrich → persist |
| `app/queries.py` | Insights aggregations (unit-tested), NL query, relationship graph |
| `app/reports.py` | Auto-generated leadership action report |
| `app/main.py` | FastAPI routes |
| `app/templates/`, `app/static/` | The dashboard SPA |

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your LLM key
cp .env.example .env          # then edit .env and paste your OpenRouter key
#    OPENROUTER_API_KEY=sk-or-...
#    MODEL=google/gemini-2.0-flash-001   (swap to any OpenRouter model id)

# 3. Seed sample meetings (also smoke-tests the pipeline)
python seed.py --reset

# 4. Run
uvicorn app.main:app --reload
# open http://127.0.0.1:8000   (API docs at /docs)
```

Any OpenRouter model works — change one line in `.env`. Recommended defaults:
`google/gemini-2.0-flash-001`, `openai/gpt-4o-mini`, or `anthropic/claude-3.5-haiku`.

---

## Demo script (≈3 minutes)

1. **Open the dashboard.** Point out the KPI strip (open escalations, projects at risk,
   owner gaps, duplicates) — already populated from seeded meetings.
2. **Ingest live.** Paste the PDF's scenario into the left panel and click *Extract
   intelligence*:
   > "The payment integration is delayed because the Vendor API is unstable. Rahul will
   > coordinate with the backend team before Friday. If this issue continues, it may impact
   > the Phase-2 release. Priya escalated the concern to leadership."

   Show the extracted badges (project, escalation, owner, deadline, risk, priority,
   sentiment) — matching the PDF's "Expected AI Output".
3. **Escalations tab.** Show severity bars (the scoring engine) and the **duplicate**
   badge on the repeated Vendor API escalation across meetings.
3b. **Meetings tab.** Click *View transcript* on any meeting to show the **original raw
   text side-by-side with what the AI extracted** from it — the clearest way to prove the
   "unstructured → structured" transformation.
4. **Ask in English** (use the example chips):
   - "What are the current unresolved escalations?"
   - "Show all pending tasks assigned to Rahul." (note he appears across multiple meetings)
   - "Which projects are at risk this week?"
   Point out the cited source meetings — answers are grounded, not hallucinated.
5. **Insights tab.** Workload bars, escalation trend, top risks, cross-team dependency map.
6. **Graph tab.** The people ↔ projects ↔ tasks ↔ escalations relationship map.
7. **Report tab.** Click *Generate leadership action report* → an auto-written Markdown
   action summary.

---

## Requirements coverage

| Spec requirement | Where |
|---|---|
| Accept summaries / transcripts / uploaded files | `POST /api/ingest`, `POST /api/ingest/file` |
| Extract tasks, escalations, blockers, risks, decisions, deadlines, ownership | `llm.extract_meeting` + `extraction.py` |
| Structured, queryable storage + relationships | `models.py` (FK graph), `queries.build_graph` |
| Conversational natural-language querying | `POST /api/query` (`queries.nl_query`) |
| Org insight generation (trends/health/workload/gaps/deps) | `GET /api/insights` (`compute_insights`) |

### Bonus features implemented
- ✅ **Risk severity scoring & prioritization** (`enrich.severity_score`)
- ✅ **Duplicate escalation detection across meetings** (`enrich.is_duplicate_escalation`)
- ✅ **Real-time leadership dashboard** (the SPA)
- ✅ **Auto-generated follow-up / action report** (`reports.build_report`)
- ✅ **Sentiment & urgency analysis** (per meeting, from extraction)
- ✅ **Voice-based ingestion** — click 🎤 Speak and dictate the meeting straight into the
  transcription box (browser-native Web Speech API; works in Chrome/Edge, no key needed)

### Future work (designed for, not built)
Multi-agent orchestration · vector/semantic search (Chroma/FAISS) · Slack/Teams
notifications.

---

## Tests

```bash
pytest -q
```
Deterministic logic (entity resolution, severity scoring, duplicate detection, insight
aggregations) is unit-tested so the live demo can't be surprised by the model. LLM calls
are not hit in tests.
