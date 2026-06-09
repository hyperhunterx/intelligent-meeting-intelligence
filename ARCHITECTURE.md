# IMIES — Architecture & How It Works

A demo-ready walkthrough of the codebase: the tech stack and *why*, the layered
architecture, the request/data flows, and how the app actually runs.

---

## 1. One-paragraph pitch

IMIES takes raw, messy meeting text and turns it into structured, queryable
organizational intelligence. The core architectural idea: **the LLM is used exactly
twice** — once on the way *in* to extract structure from chaos, and once on the way
*out* to answer English questions over that structure. Everything in between is a
normal relational database and deterministic Python. The AI never invents your data;
it only reads from a real database — which makes the system reliable, explainable,
and fast.

---

## 2. Tech stack — what & why

| Layer | Tech | Why |
|---|---|---|
| Language | **Python 3.11** | Best ecosystem for AI/data; fast to build. |
| Web framework | **FastAPI** | Async, auto-generated API docs (`/docs`), native Pydantic validation. Chosen over Flask for typing + validation + docs out of the box. |
| Server | **Uvicorn** | The ASGI server that actually runs the FastAPI app (see §6). |
| Database | **SQLite + SQLAlchemy** | Zero setup — the whole DB is one file (`imies.db`). SQLAlchemy (ORM) lets us write Python instead of raw SQL. Chosen over Neo4j to avoid Docker/install risk while still modeling the graph via foreign keys. |
| Validation | **Pydantic** | Forces the LLM output into a typed schema — the contract that makes extraction reliable. |
| AI access | **OpenRouter** via the **OpenAI SDK** | One API reaching Claude/GPT/Gemini. Vendor-neutral — swap the model with one line in `.env`. |
| Frontend | **Vanilla HTML/CSS/JS** | No build step, loads instantly, served directly by FastAPI — keeps everything one process. |
| Tests | **pytest** | Locks down deterministic logic so a live demo can't silently break. |
| Email | **smtplib (SMTP)** | Standard-library email; the app sends the action report itself. |

---

## 3. Layered architecture & file responsibilities

```
PRESENTATION   templates/index.html · static/app.js · static/styles.css   (the dashboard SPA)
API            app/main.py            FastAPI routes (the HTTP surface)
BUSINESS LOGIC extraction.py  ingest pipeline (orchestrator)
               queries.py     insights + natural-language query + graph
               enrich.py      PURE logic: severity scoring, dedup, name-normalize
               reports.py     action report builder
               email_send.py  SMTP sender        files.py  pdf/docx text extraction
AI             app/llm.py     OpenRouter client (extract / answer / report)
DATA           models.py  ORM tables   db.py  engine/session   schemas.py  Pydantic contracts
               config.py  settings loaded from .env
```

Each file has one job. The AI is isolated in `llm.py`; the deterministic logic in
`enrich.py` is unit-tested; orchestration reads top-to-bottom in `extraction.py`.

---

## 4. Flow #1 — INGEST (raw text → structured data)

```
Browser ──POST /api/ingest {text}──► main.py
  └─► extraction.ingest_meeting(session, text)
        1. llm.extract_meeting(text)                ← AI CALL #1
             • text + strict "return JSON in THIS shape" prompt
             • OpenRouter → model → JSON → Pydantic-validated MeetingExtraction
             • bad JSON? retry once stricter, then degrade gracefully (never crashes)
        2. ENRICH (pure Python, no AI):
             • normalize_name()        "Rahul" == "rahul" == " RAHUL "
             • severity_score()        0–100 from priority + escalation + keywords
             • is_duplicate_escalation flags repeats across meetings
        3. get-or-create People & Projects by normalized name
             → same "Rahul" across meetings = ONE row (cross-meeting linking)
        4. write Meeting + Tasks + Escalations + Risks + Blockers +
             Decisions + OpenQuestions + FollowUps, linked by foreign keys
        5. session.commit()
  └─► returns {counts, sentiment, urgency} → dashboard refreshes
```

The model only decides *what the data is* in step 1. After that, scoring, deduping,
and saving are deterministic.

---

## 5. Flow #2 — QUERY (English question → grounded answer)

```
Browser ──POST /api/query {question}──► main.py
  └─► queries.nl_query(session, question)
        1. RETRIEVE (deterministic): score every record by
             +3 if the question names its type (escalation/task/risk/…)
             +1 per question keyword found in the record
           → take top-scoring records (searches ALL types + meeting summaries)
        2. llm.answer_query(question, records)       ← AI CALL #2
             • "Answer ONLY from these records, cite the meetings"
  └─► returns {answer, sources} → dashboard shows answer + source meetings
```

This is "RAG-lite": retrieve the relevant rows first, then ask the model to answer
*only* from those and cite them — grounded, not hallucinated.

### Flow #3 — INSIGHTS (`GET /api/insights`)
Pure SQL aggregations (escalation counts, workload per person, project health). **No
AI** — instant and demo-safe.

---

## 6. How it runs — `uvicorn app.main:app --reload`

- **`uvicorn`** — the **server**. FastAPI is *not* a server; it's a Python object
  describing routes. Uvicorn opens the network port, accepts HTTP, and calls our code.
  FastAPI = the rulebook; Uvicorn = the engine.
- **`app.main:app`** — *where to find it*: package `app`, file `main.py`, variable `app`.
- **`--reload`** — auto-restart on file change. **Development only.**

**ASGI:** Uvicorn is an ASGI server — the async successor to WSGI. ASGI handles many
requests concurrently, which matters because our requests wait on slow LLM API calls.

**Why not `--reload` for the demo:** it spawns a watcher + worker; the worker can
survive and keep holding the port (the "ghost server / stale 404" problem). For demos
use a plain `uvicorn app.main:app` or **`run.bat`** (kills stale servers, auto-picks a
free port, opens the browser) — a single clean process you stop with `Ctrl+C`.

**Request lifecycle:**
```
Browser → Uvicorn → FastAPI matches route → Depends(get_session) opens a DB session →
handler runs (extraction / queries / llm) → returns JSON/HTML → Uvicorn responds → session closed
```

---

## 7. Data model — "a graph, stored in tables"

Not a graph database — we model the graph with **foreign keys in SQLite**, getting the
relationships without Neo4j's setup overhead.

- **Nodes:** `meetings`, `people`, `projects`
- **Items:** `tasks`, `escalations`, `risks`, `blockers`, `decisions`, `open_questions`, `follow_ups`
- **Relationships (exactly per the spec):**
  - `Person —assigned_to→ Task` (`Task.owner_id`)
  - `Escalation —raised_by→ Person` (`Escalation.raised_by_id`)
  - `Project —has_blocker→ Blocker`; every item `—belongs_to→ Project`
  - `Meeting —contains→` every item
- **`/api/graph`** walks these foreign keys → nodes + edges for the relationship view.

---

## 8. API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/ingest` | Ingest meeting text → structured intelligence |
| POST | `/api/ingest/file` | One-shot ingest of an uploaded `.txt/.md/.pdf/.docx` |
| POST | `/api/extract-text` | Extract a file's text into the editor (no ingest) |
| POST | `/api/query` | Natural-language question → grounded answer + sources |
| GET | `/api/insights` | Org-wide aggregate intelligence |
| GET | `/api/graph` | Relationship nodes + edges |
| POST | `/api/report` | Auto-generated action report (Markdown) |
| POST | `/api/report/email` | Generate the report **and email it** (SMTP) |
| GET | `/api/meetings` `/api/meetings/{id}` | List feeds + full meeting (raw + extracted) |
| DELETE | `/api/meetings/{id}` | Delete a meeting + all its data (with orphan sweep) |
| GET | `/api/escalations` `/api/tasks` `/api/projects` | Dashboard feeds |

---

## 9. Likely judge questions

- **Bad JSON from the LLM?** Validated with Pydantic; retry once stricter, then safe
  empty fallback. Never crashes.
- **Hallucinations?** Queries are grounded — retrieve real rows, answer only from them, cite sources.
- **Why not a vector DB?** Type + keyword scoring over structured data is fast and
  explainable; semantic/vector search is designed-for future work.
- **Swap the AI model?** One line in `.env` (OpenRouter).
- **Tested?** 23 passing unit tests cover the deterministic core (scoring, dedup,
  insights, orphan cleanup); AI calls verified manually.
