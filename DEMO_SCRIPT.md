# IMIES — Demonstration Script (~6–7 minutes)

A step-by-step script: what to do, what to click, and what to say.

---

## 0. Before the demo (5 minutes prior — do NOT skip)

- [ ] `.env` has a valid `OPENROUTER_API_KEY` (and `SMTP_USER` / `SMTP_PASSWORD` if showing email).
- [ ] Internet is on (needed for the LLM, web fonts, and email).
- [ ] Double-click **`run.bat`** → the dashboard opens in the browser. Hard-refresh once (`Ctrl+F5`).
- [ ] **Pre-load some data so the dashboard looks alive:** upload 3 of the files from
      `data/transcripts/` (e.g. `01_engineering_infra_sync.txt`, `03_customer_support_escalations.txt`,
      `05_leadership_weekly_review.txt`). For each: **Upload file → Extract intelligence.**
      Keep the PDF scenario for the *live* moment below.
- [ ] Have ready: `sample_meeting_transcript.pdf`, and one recipient email for the report.
- [ ] (Optional) Open **`imies.db`** in SQLite Viewer in a second window for the "storage" proof.
- [ ] Keep the GitHub repo tab open: github.com/hyperhunterx/intelligent-meeting-intelligence

---

## 1. The hook (30 sec) — say this

> "Every company runs on meetings, but the intelligence inside them — the escalations,
> the action items, the risks — gets buried in transcripts and lost. **IMIES turns raw
> meeting text into structured, searchable organizational intelligence using GenAI.**
> The core idea: we use the LLM twice — once to *extract* structure from messy text, and
> once to *answer* questions over it. Everything in between is a real database, so the AI
> never invents data — it reads from facts."

Gesture at the populated dashboard — KPI strip (open escalations, projects at risk, etc.).

---

## 2. Live ingestion — the "wow" moment (90 sec)

This is the moment to use the **exact scenario from the problem statement** (judges recognize it).

1. Paste into the ingest box:
   > "The payment integration is delayed because the Vendor API is unstable. Rahul will
   > coordinate with the backend team before Friday. If this issue continues, it may impact
   > the Phase-2 release. Priya escalated the concern to leadership."
2. Click **Extract intelligence.** (Takes ~2–3 seconds.)
3. Say: *"In real time, the AI pulled out the project, the blocker, the owner Rahul, the
   Friday deadline, the Phase-2 risk, Priya's escalation, the Backend Team, and priority
   High — exactly the structured output the brief asked for, plus sentiment and an
   escalation severity score of 85."*
4. Click the **Escalations** tab → point at the **severity bars** and, if a Vendor-API
   escalation repeats, the **duplicate** badge: *"It even detects the same escalation
   raised across different meetings."*

*(Bonus line: mention you can also dictate by voice — click 🎤 Speak — or upload a PDF/DOCX.)*

---

## 3. Ask in plain English (60 sec)

Go to **"Ask your organization."** Click the example chips or type:

- *"What are the current unresolved escalations?"* → grounded answer + **cited source meetings**.
- *"Show all pending tasks assigned to Rahul."* → *"Notice Rahul appears across multiple
  meetings — the system links the same person everywhere."*
- *"Which projects are at risk this week?"*

Say: *"These answers are grounded — it retrieves the real records first, then answers only
from them and cites which meeting each fact came from. No hallucination."*

---

## 4. Organizational insight (45 sec)

Click the **Insights** tab:
- Team workload (open tasks per owner), escalation trend, top risks by severity, cross-team
  dependency map. Say: *"This is all deterministic SQL — no AI — so it's instant and always
  accurate. This is the leadership-visibility view."*

Click the **Graph** tab:
- *"This is the knowledge graph — people, projects, tasks, and escalations and how they
  connect."* **Hover a node** → connections highlight. **Click it** → *"and I can pin a
  node to trace everything it touches."*

---

## 5. Action report + email (45 sec)

Click the **Report** tab → **Generate action report** → a leadership-ready Markdown summary appears.
Then type an email and click **✉ Email it** → *"and it sends that report as a formatted email,
right from the app."* (Show the inbox if you set up SMTP.)

---

## 6. Architecture & storage (45 sec)

- (If SQLite Viewer is open) switch to it: *"Everything lives in a structured, queryable
  SQLite database — meetings, people, projects, tasks, escalations — all linked by foreign
  keys, which is how we model the knowledge graph."*
- One line on the stack: *"FastAPI backend, SQLite storage, and OpenRouter for the LLM — so
  we can swap between Claude, GPT, or Gemini with a one-line config change."*

---

## 7. Close (20 sec)

> "So IMIES covers the full brief — multi-format ingestion, AI extraction, structured
> interconnected storage, natural-language querying, and org-wide insights — plus bonus
> features: risk severity scoring, duplicate detection, sentiment, a live dashboard,
> voice input, and auto-generated email reports. It's all open-source on GitHub. Thank you."

---

## Q&A — quick answers

| Question | Answer |
|---|---|
| What if the LLM returns bad JSON? | Pydantic validates it; we retry once stricter, then fall back safely. Never crashes. |
| How do you prevent hallucinations? | Queries are grounded — retrieve real DB rows, answer only from them, cite sources. |
| Why SQLite, not Neo4j? | We model the graph with foreign keys — relationships without the setup overhead. Zero install. |
| Can you change the AI model? | Yes — one line in `.env`. OpenRouter reaches Claude/GPT/Gemini. |
| Is it tested? | 23 unit tests on the deterministic core (scoring, dedup, insights, cleanup). |
| What's not built / future work? | Multi-agent orchestration, vector/semantic search, Slack/Teams — designed for, time-boxed out. |

---

## Timing cheat-sheet
Hook 0:30 · Live ingest 1:30 · Query 1:00 · Insights+Graph 0:45 · Report+Email 0:45 ·
Architecture 0:45 · Close 0:20  → **~5:35** core, ~7 min with Q&A buffer.

## If something fails (stay calm)
- LLM slow/down → switch `MODEL` in `.env`, or fall back to the pre-loaded data + Insights/Graph (no AI needed).
- Port stuck → re-run `run.bat` (auto-picks a free port).
- Email not set up → just show the generated report; the email is a bonus.
