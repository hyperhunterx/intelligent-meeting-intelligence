# IMIES Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox (`- [ ]`) syntax.
> Inline execution in the build session, with explanation at each task (demo-oriented).

**Goal:** Build an AI system that ingests raw meeting text and turns it into structured,
queryable, interconnected organizational intelligence (escalations, tasks, risks, owners,
projects), exposed via FastAPI + natural-language query + a leadership dashboard.

**Architecture:** FastAPI backend; LLM (via OpenRouter, OpenAI-compatible) used twice —
to EXTRACT structure on ingest and to ANSWER English questions over a SQLite database;
deterministic SQL for insights; Pydantic for schema safety; a single-page dashboard.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy, SQLite, Pydantic, `openai` SDK
(pointed at OpenRouter), pytest, vanilla HTML/CSS/JS + a small charting lib.

---

## File structure (locked)

```
app/
  __init__.py
  config.py        # Settings from .env (OPENROUTER_API_KEY, MODEL, DB path)
  db.py            # SQLAlchemy engine + session + init
  models.py        # ORM: Meeting, Person, Project, Task, Escalation, Risk, Blocker, Decision (+links)
  schemas.py       # Pydantic: extraction output schema + API request/response models
  enrich.py        # PURE logic: normalize_name, severity_score, is_duplicate_escalation  (TDD)
  llm.py           # OpenRouter client; extract_meeting(), answer_query(), generate_report()
  extraction.py    # ingest pipeline: text -> llm extract -> enrich -> persist
  queries.py       # nl_query() + insights aggregations (SQL)  (insights TDD)
  reports.py       # auto action report builder
  main.py          # FastAPI app, routes, static/template mounting
  templates/index.html
  static/app.js
  static/styles.css
tests/
  test_enrich.py
  test_insights.py
data/sample_meetings.json
.env.example   requirements.txt   README.md   PROGRESS.md
```

---

### Task 0: Scaffold project + dependencies

**Files:** Create `requirements.txt`, `.env.example`, `app/__init__.py`, `app/config.py`, `.gitignore`

- [ ] **Step 1:** Write `requirements.txt`:
```
fastapi
uvicorn[standard]
sqlalchemy
pydantic
pydantic-settings
python-dotenv
openai
python-multipart
pytest
httpx
```
- [ ] **Step 2:** Write `.gitignore` (`.env`, `__pycache__/`, `*.db`, `.pytest_cache/`, `venv/`).
- [ ] **Step 3:** Write `.env.example`:
```
OPENROUTER_API_KEY=sk-or-...
MODEL=google/gemini-2.0-flash-001
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DB_PATH=imies.db
```
- [ ] **Step 4:** Write `app/config.py` using pydantic-settings `BaseSettings` reading those vars.
- [ ] **Step 5:** `pip install -r requirements.txt`.
- [ ] **Step 6:** Commit `chore: scaffold project`.

---

### Task 1: Database models

**Files:** Create `app/db.py`, `app/models.py`

- [ ] **Step 1:** `app/db.py` — SQLAlchemy engine (SQLite from `settings.DB_PATH`), `SessionLocal`, `Base`, `init_db()`, `get_session()` dependency.
- [ ] **Step 2:** `app/models.py` — ORM classes:
  - `Meeting(id, title, raw_text, source_type, summary, sentiment, urgency, created_at)`
  - `Person(id, name UNIQUE-normalized, team)`
  - `Project(id, name UNIQUE-normalized, status)`
  - `Task(id, description, owner_id→Person, project_id→Project, meeting_id→Meeting, deadline, status, priority)`
  - `Escalation(id, description, raised_by_id→Person, project_id, meeting_id, severity_score, status, created_at, duplicate_of_id→Escalation nullable)`
  - `Risk(id, description, project_id, meeting_id, severity, impact)`
  - `Blocker(id, description, project_id, meeting_id, status)`
  - `Decision(id, description, rationale, project_id, meeting_id)`
  - `meeting_participants` (meeting↔person), `item_teams` simplified as `Task.teams`/`Escalation.teams` JSON column for time.
- [ ] **Step 3:** Smoke test: `python -c "from app.db import init_db; init_db()"` creates the DB.
- [ ] **Step 4:** Commit `feat: db models`.

---

### Task 2: Pydantic schemas (extraction contract)

**Files:** Create `app/schemas.py`

- [ ] **Step 1:** Define extraction output models mirroring the PDF "Expected AI Output":
```python
class ExtractedTask(BaseModel):
    description: str; owner: str|None=None; deadline: str|None=None
    priority: str|None=None; project: str|None=None; teams: list[str]=[]
class ExtractedEscalation(BaseModel):
    description: str; raised_by: str|None=None; project: str|None=None
    priority: str|None=None; teams: list[str]=[]
class ExtractedRisk(BaseModel):
    description: str; project: str|None=None; impact: str|None=None; priority: str|None=None
class ExtractedBlocker(BaseModel):
    description: str; project: str|None=None; status: str|None=None
class ExtractedDecision(BaseModel):
    description: str; rationale: str|None=None; project: str|None=None
class MeetingExtraction(BaseModel):
    title: str|None=None; summary: str|None=None
    sentiment: str|None=None; urgency: str|None=None
    projects: list[str]=[]; people: list[str]=[]
    tasks: list[ExtractedTask]=[]; escalations: list[ExtractedEscalation]=[]
    risks: list[ExtractedRisk]=[]; blockers: list[ExtractedBlocker]=[]
    decisions: list[ExtractedDecision]=[]
```
- [ ] **Step 2:** API I/O models: `IngestRequest{text, title?, source_type?}`, `QueryRequest{question}`, `QueryResponse{answer, sources}`, `ReportRequest{scope?, project?}`.
- [ ] **Step 3:** Commit `feat: pydantic schemas`.

---

### Task 3 (TDD): enrich.py — pure logic

**Files:** Create `tests/test_enrich.py`, `app/enrich.py`

- [ ] **Step 1: Failing tests** (`tests/test_enrich.py`):
```python
from app.enrich import normalize_name, severity_score, is_duplicate_escalation
def test_normalize_name():
    assert normalize_name("  Rahul ") == "rahul"
    assert normalize_name("Backend Team") == "backend team"
def test_severity_high_priority_escalation():
    s = severity_score(priority="high", is_escalation=True, text="blocker outage critical")
    assert s >= 70
def test_severity_low():
    assert severity_score(priority="low", is_escalation=False, text="minor note") < 40
def test_duplicate_detection():
    existing = [{"description":"Vendor API is unstable","project":"payment integration"}]
    assert is_duplicate_escalation("vendor api unstable", "Payment Integration", existing) is True
    assert is_duplicate_escalation("hiring is slow", "Recruiting", existing) is False
```
- [ ] **Step 2:** Run `pytest tests/test_enrich.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `app/enrich.py`:
  - `normalize_name(s)` → `s.strip().lower()`.
  - `severity_score(priority, is_escalation, text)` → base from priority map (high=60,medium=35,low=15,None=25); +20 if escalation; +keyword bumps (critical/outage/blocker/security/breach/down) capped at 100.
  - `is_duplicate_escalation(desc, project, existing)` → `difflib.SequenceMatcher` ratio ≥0.6 on normalized desc AND same normalized project.
- [ ] **Step 4:** Run tests → PASS.
- [ ] **Step 5:** Commit `feat: enrich logic (TDD)`.

---

### Task 4: LLM client (OpenRouter)

**Files:** Create `app/llm.py`

- [ ] **Step 1:** OpenAI client with `base_url=settings.OPENROUTER_BASE_URL`, `api_key=settings.OPENROUTER_API_KEY`.
- [ ] **Step 2:** `extract_meeting(text) -> MeetingExtraction`: system prompt instructs strict JSON matching schema; call with `response_format={"type":"json_object"}`; parse → validate Pydantic; on failure retry once with stricter prompt; fallback to empty `MeetingExtraction(summary=text[:200])`.
- [ ] **Step 3:** `answer_query(question, context_rows) -> str`: prompt with retrieved DB rows as JSON context; instruct grounded answer citing meeting titles; return text.
- [ ] **Step 4:** `generate_report(open_items) -> str`: prompt to produce a crisp markdown follow-up/action report.
- [ ] **Step 5:** Manual smoke (only if key present): extract the PDF scenario, print JSON. Commit `feat: llm client`.

---

### Task 5: Ingestion pipeline

**Files:** Create `app/extraction.py`

- [ ] **Step 1:** `ingest_meeting(session, text, title, source_type) -> dict`:
  1. `extraction = llm.extract_meeting(text)`
  2. get-or-create `Project`/`Person` by `normalize_name`.
  3. create `Meeting` (+ sentiment/urgency/summary), link participants.
  4. for each task/risk/blocker/decision → create rows linked to project+meeting+owner.
  5. for each escalation → compute `severity_score`; check `is_duplicate_escalation` vs existing open escalations (set `duplicate_of_id`); persist.
  6. commit; return a summary dict (counts + the structured extraction) for the UI.
- [ ] **Step 2:** Smoke via a throwaway script against sample text. Commit `feat: ingestion pipeline`.

---

### Task 6 (TDD): queries.py — insights aggregations

**Files:** Create `tests/test_insights.py`, `app/queries.py`

- [ ] **Step 1: Failing test** — seed an in-memory/temp DB with 2 meetings, 2 escalations (1 high), 3 tasks (2 to Rahul); assert:
```python
def test_insights_counts(seeded_session):
    ins = compute_insights(seeded_session)
    assert ins["open_escalations"] >= 1
    assert ins["workload"]["rahul"] == 2
    assert "project_health" in ins
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `compute_insights(session)`: SQL aggregations →
  open_escalations, escalation_trend (by day), project_health (per project: #blockers/#risks/#open tasks → status label), workload (tasks per owner), accountability_gaps (tasks with no owner / overdue), top_risks (by severity), dependency map (project→teams).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Implement `nl_query(session, question)`: lightweight retrieval — pull candidate rows (escalations/tasks/risks/projects/meetings) optionally filtered by keywords the LLM/keyword-extractor returns, pass to `llm.answer_query`, return `{answer, sources}`.
- [ ] **Step 6:** Commit `feat: insights + nl query`.

---

### Task 7: Reports + graph

**Files:** Create `app/reports.py`; add `graph` builder (in `queries.py`)

- [ ] **Step 1:** `build_report(session, scope, project)`: gather open tasks/escalations/risks → `llm.generate_report`.
- [ ] **Step 2:** `build_graph(session)`: return `{nodes:[{id,label,type}], edges:[{source,target,label}]}` from people/projects/tasks/escalations.
- [ ] **Step 3:** Commit `feat: reports + graph`.

---

### Task 8: FastAPI app + routes

**Files:** Create `app/main.py`

- [ ] **Step 1:** App init, `init_db()` on startup, mount `static/`, Jinja templates.
- [ ] **Step 2:** Routes:
  - `GET /` → dashboard `index.html`
  - `POST /api/ingest` (JSON text OR file upload via `UploadFile`) → `ingest_meeting`
  - `POST /api/query` → `nl_query`
  - `GET /api/insights` → `compute_insights`
  - `GET /api/graph` → `build_graph`
  - `GET /api/meetings|escalations|tasks|projects` → list endpoints
  - `POST /api/report` → `build_report`
- [ ] **Step 3:** Run `uvicorn app.main:app --reload`; hit `/docs`. Commit `feat: api routes`.

---

### Task 9: Dashboard (SPA)

**Files:** Create `app/templates/index.html`, `app/static/styles.css`, `app/static/app.js`

- [ ] **Step 1:** Layout: header; left = ingest panel (textarea + file upload + "Extract") and NL query box; right/main = tabs: **Escalations** (severity-sorted, dup badges), **Projects health**, **Tasks/Owners**, **Insights** (charts: escalation trend, workload), **Graph** (relationship map), **Report** (generate button + rendered markdown).
- [ ] **Step 2:** `app.js` — fetch calls to each endpoint; render tables/cards; draw charts (lightweight: inline SVG/Canvas or a tiny CDN lib); graph via simple force/positioned SVG.
- [ ] **Step 3:** Use frontend-design skill for a polished, distinctive look (dark, dashboard aesthetic).
- [ ] **Step 4:** Commit `feat: dashboard`.

---

### Task 10: Seed data + README + run script

**Files:** Create `data/sample_meetings.json`, `README.md`, `seed.py`

- [ ] **Step 1:** `data/sample_meetings.json` — 4–5 realistic meetings incl. the PDF payment-integration scenario, with overlapping people/projects and a deliberate duplicate escalation across two meetings (to demo dup detection) and varied priorities.
- [ ] **Step 2:** `seed.py` — loops sample meetings through `ingest_meeting` to populate the DB for an instant-alive demo.
- [ ] **Step 3:** `README.md` — setup (venv, install, `.env`), run, demo script (the exact clicks/queries to show judges), architecture summary, requirements-coverage checklist, bonus list.
- [ ] **Step 4:** Commit `docs: seed data + README`.

---

### Task 11: End-to-end verification

- [ ] **Step 1:** Fresh `.env` with real key; `python seed.py`; `uvicorn app.main:app`.
- [ ] **Step 2:** Verify each PDF example NL query returns a sensible grounded answer.
- [ ] **Step 3:** Verify dashboard tabs all render with seeded data; dup escalation flagged; report generates.
- [ ] **Step 4:** Run `pytest` → all green. Update `PROGRESS.md`. Commit `test: e2e verification`.

---

## Requirements coverage check (self-review)

| Spec requirement | Task |
|---|---|
| Meeting input: summaries/transcripts/uploaded files | T8 (text + file upload) |
| Extract tasks, escalations, blockers, risks, decisions, deadlines, ownership | T2,T4,T5 |
| Structured queryable storage + relationships | T1,T5,T7 (graph) |
| Conversational NL querying | T6 (nl_query), T8 |
| Org insight generation (trends/health/workload/gaps/deps) | T6 (compute_insights) |
| Bonus: risk severity scoring | T3 |
| Bonus: duplicate escalation detection | T3,T5 |
| Bonus: leadership dashboard | T9 |
| Bonus: auto follow-up/action report | T7 |
| Bonus: sentiment/urgency | T2,T4,T5 |
