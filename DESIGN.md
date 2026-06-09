# Design — Intelligent Meeting Intelligence & Escalation Tracking System (IMIES)

> GenAI Hackathon project. Converts unstructured meeting content into structured,
> queryable, interconnected organizational intelligence. Audience: hackathon judges.
> Build window: ~5–6 hours.

## 1. Goal (from the spec)

Ingest raw meeting content (summaries, transcripts, uploaded files) and automatically
**extract → structure → interconnect** the intelligence hidden inside: projects, action
items & ownership, escalations/blockers, risks & cross-team dependencies, stakeholders,
deadlines, priorities, decisions, and follow-ups. Store it queryably, link it
contextually, and expose it via API + natural-language queries + a leadership dashboard.

## 2. Chosen stack

| Concern | Choice | Rationale |
|---|---|---|
| LLM access | **OpenRouter** (OpenAI-compatible SDK), model via `MODEL` env var | Vendor-neutral; swap brains in one line. Default to a fast JSON-strong model. |
| Backend / API | **FastAPI** | Async, auto Swagger, easy static serving. Spec requires an API endpoint. |
| Storage | **SQLite + SQLAlchemy** | Zero setup, fully queryable, relational links model the required graph. |
| Graph view | In-app `/api/graph` nodes+edges visualization | Neo4j-style relationship map without Docker/install risk. |
| Frontend | **Single-page dashboard** served by FastAPI | Best "leadership real-time visibility" demo. |
| Validation | **Pydantic** | Forces LLM output into a typed schema; retry on bad JSON. |
| Tests | **pytest**, TDD on pure logic | Deterministic pieces locked down; LLM mocked. |

## 3. Data flow

```
Raw meeting text ──► [LLM extraction] ──► structured JSON
        │                                      │
        │                          [enrich: dedupe people/projects,
        │                           score risk severity, flag duplicate
        │                           escalations, sentiment]
        │                                      │
        ▼                                      ▼
   POST /api/ingest ───────────────► SQLite (the org's memory)
                                              │
        ┌──────────────────┬──────────────────┼──────────────────┐
        ▼                  ▼                   ▼                  ▼
  POST /api/query   GET /api/insights    GET /api/graph    Dashboard (SPA)
  (ask in English)  (org-wide stats)     (relationship map)
```

**Core principle:** the LLM is used twice — to **extract** structure from messy text, and
to **answer** English questions over already-structured data. Everything between is
deterministic SQL. The AI never invents your data; it reads from a real database. This is
what makes the system reliable and explainable.

## 4. Storage model (the "graph in tables")

Nodes: `meetings`, `people`, `projects`.
Items: `tasks`, `escalations`, `risks`, `blockers`, `decisions` — each linked to a meeting,
usually a project, and (where relevant) a person.
Link tables: `meeting_participants`, `item_teams` (many-to-many teams/stakeholders),
`task_dependencies` / `risk_dependencies` as needed.

Encoded relationships (matching the spec):
- `Person —assigned_to→ Task`
- `Project —has_blocker→ Blocker/Issue`
- `Escalation —raised_by→ Person`
- `Task/Escalation/Risk —belongs_to→ Project`
- `Meeting —contains→ {all extracted items}`

**Entity resolution:** people and projects are **get-or-create by normalized name**, so the
same "Rahul" across meetings is ONE node linked to all of them — this is what enables
cross-meeting accountability tracking.

## 5. The two LLM jobs

**Extraction (ingest).** One structured prompt → validated JSON (Pydantic schema). On bad
JSON: retry once with stricter instructions, then fall back to an empty-but-flagged result.
Output mirrors the PDF's "Expected AI Output" exactly: Project / Blocker / Owner / Deadline
/ Risk / Escalation-by / Teams / Priority (+ decisions, follow-ups, sentiment).

**Querying (NL).** Hybrid grounded retrieval: LLM converts the English question into DB
filters → we pull matching rows → LLM composes the answer **citing the source meetings**.
Grounded, not hallucinated. Handles the spec's example questions
("current unresolved escalations?", "projects at risk this week?", "pending tasks for Rahul",
"meetings discussing Vendor API", "high-priority blockers across teams").

## 6. Insights (`/api/insights`) — deterministic SQL

Escalation trends over time · project health/risk status · pending-action accountability
gaps · team workload distribution · dependency/risk mapping. Pure aggregations — no LLM,
always works, demo-safe.

## 7. API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ingest` | Ingest meeting text or uploaded file → extracted structured intelligence |
| POST | `/api/query` | Natural-language question → grounded answer + sources |
| GET | `/api/insights` | Org-wide aggregate intelligence |
| GET | `/api/graph` | Nodes + edges for relationship visualization |
| GET | `/api/meetings` `/api/escalations` `/api/tasks` `/api/projects` | List/detail feeds for dashboard |
| POST | `/api/report` | Auto-generated follow-up/action report (per project or org-wide) |

## 8. Bonuses folded in (cheap, high-impact)

1. **Risk severity scoring** — numeric 0–100 from priority + escalation status + keyword signals.
2. **Duplicate escalation detection** — text similarity + same-project flagging across meetings.
3. **Leadership dashboard** — the polished SPA.
4. **Auto-generated action report** — LLM per-project follow-up/email summary from open items.
5. **Sentiment / urgency** — per-meeting tone field from extraction.

**Deferred (named as "future" in the demo):** multi-agent orchestration, vector/Chroma
semantic search, Slack/Teams notifications, voice ingestion.

## 9. Project structure

```
app/
  main.py        # FastAPI app + routes
  config.py      # env/settings (.env)
  db.py          # SQLAlchemy engine/session
  models.py      # ORM models
  schemas.py     # Pydantic schemas (extraction output + API I/O)
  llm.py         # OpenRouter client + extraction/query/report prompts
  extraction.py  # ingest pipeline orchestration
  enrich.py      # severity scoring, dedup, entity resolution (pure, TDD-tested)
  queries.py     # NL query + insights aggregations
  reports.py     # auto action report
  static/        # dashboard JS/CSS
  templates/     # dashboard HTML
tests/           # pytest (pure logic; LLM mocked)
data/            # seed sample meetings (incl. PDF scenario)
docs in root:    DESIGN.md · PLAN.md · PROGRESS.md · README.md
.env.example · requirements.txt
```

## 10. Error handling & reliability

- LLM calls wrapped with retry + Pydantic validation; graceful degraded result on failure.
- File upload: accept `.txt` / `.md` (+ raw paste). PDF optional/stretch.
- DB: get-or-create avoids duplicate people/projects.
- Config strictly via `.env` (`OPENROUTER_API_KEY`, `MODEL`); never hard-coded.
- Pure logic (scoring, dedup, insights) is deterministic and unit-tested so the live demo
  cannot be surprised by the model.

## 11. Out of scope

Authentication, multi-tenant, production deployment, real Slack/voice integrations,
vector DB. Mentioned as future work only.
