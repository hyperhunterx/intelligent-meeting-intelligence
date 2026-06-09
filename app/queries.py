"""Read-side: organizational insights + natural-language querying + graph.

- compute_insights(): pure SQL aggregations for the leadership dashboard. No LLM,
  fully deterministic — these numbers are demo-safe.
- nl_query(): grounded NL question answering. We RETRIEVE candidate rows from the
  DB (keyword-filtered), then let the LLM compose an answer from only those rows.
- build_graph(): nodes+edges for the relationship visualization.
"""
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app import llm
from app.enrich import normalize_name
from app.models import (
    Meeting, Person, Project, Task, Escalation, Risk, Blocker, Decision,
    OpenQuestion, FollowUp,
)


# ---------------- Insights (deterministic) ----------------

def compute_insights(session: Session) -> dict:
    """Aggregate org-wide intelligence for the dashboard."""
    escalations = session.query(Escalation).all()
    tasks = session.query(Task).all()
    risks = session.query(Risk).all()
    projects = session.query(Project).all()

    open_escalations = [e for e in escalations if e.status == "open"]

    # Escalation trend: count per calendar day.
    trend = defaultdict(int)
    for e in escalations:
        if e.created_at:
            trend[e.created_at.strftime("%Y-%m-%d")] += 1
    escalation_trend = [{"date": d, "count": c} for d, c in sorted(trend.items())]

    # Workload: open tasks per owner (by display name).
    workload = Counter()
    accountability_gaps = 0
    for t in tasks:
        if t.status == "open":
            if t.owner:
                workload[t.owner.display_name or t.owner.name] += 1
            else:
                accountability_gaps += 1   # open task with no owner
            if not t.deadline:
                # a deadline-less open task is also an accountability gap signal
                pass

    # Per-project health: tally open items, derive a simple status label.
    health = []
    for p in projects:
        n_open_esc = sum(1 for e in p.escalations if e.status == "open")
        n_open_tasks = sum(1 for t in p.tasks if t.status == "open")
        n_risks = len(p.risks)
        n_blockers = sum(1 for b in p.blockers if b.status == "open")
        max_sev = max([e.severity_score for e in p.escalations] +
                      [r.severity_score for r in p.risks] + [0])
        if n_open_esc > 0 or max_sev >= 70:
            status = "at_risk"
        elif n_open_tasks > 0 or n_risks > 0 or n_blockers > 0:
            status = "watch"
        else:
            status = "healthy"
        health.append({
            "project": p.display_name or p.name,
            "status": status,
            "open_escalations": n_open_esc,
            "open_tasks": n_open_tasks,
            "risks": n_risks,
            "blockers": n_blockers,
            "max_severity": max_sev,
        })

    # Top risks by severity.
    top_risks = sorted(
        [{"description": r.description,
          "project": r.project.display_name if r.project else None,
          "severity_score": r.severity_score} for r in risks],
        key=lambda x: x["severity_score"], reverse=True,
    )[:10]

    # Dependency / cross-team map: project -> set of teams touched.
    deps = defaultdict(set)
    for t in tasks:
        if t.project and t.teams:
            deps[t.project.display_name or t.project.name].update(t.teams)
    for e in escalations:
        if e.project and e.teams:
            deps[e.project.display_name or e.project.name].update(e.teams)
    dependency_map = [{"project": k, "teams": sorted(v)} for k, v in deps.items()]

    return {
        "open_escalations": len(open_escalations),
        "total_escalations": len(escalations),
        "duplicate_escalations": sum(1 for e in escalations if e.duplicate_of_id),
        "open_tasks": sum(1 for t in tasks if t.status == "open"),
        "accountability_gaps": accountability_gaps,
        "escalation_trend": escalation_trend,
        "workload": dict(workload),
        "project_health": health,
        "top_risks": top_risks,
        "dependency_map": dependency_map,
        "projects_at_risk": [h["project"] for h in health if h["status"] == "at_risk"],
    }


# ---------------- Natural-language query (grounded) ----------------

# Common stop words we don't want to match rows on.
# Words that map a question to an ENTITY TYPE we should pull wholesale.
_TYPE_WORDS = {
    "escalation": "escalation", "escalations": "escalation", "escalated": "escalation",
    "task": "task", "tasks": "task", "todo": "task", "todos": "task",
    "action": "task", "items": "task", "assignment": "task", "assignments": "task",
    "risk": "risk", "risks": "risk",
    "blocker": "blocker", "blockers": "blocker", "blocked": "blocker",
    "decision": "decision", "decisions": "decision", "decided": "decision",
}
# Words that mean "only OPEN items".
_OPEN_WORDS = {"open", "unresolved", "pending", "outstanding", "current",
               "active", "ongoing"}
# Noise we strip before keyword matching (so "projects at risk this week" -> []).
_STOP = set((
    "the a an of to in on for is are was were what which show list all give tell find get "
    "me my our your their across this that these those week weeks who whom whose and or "
    "with at by have has had please can you do does any currently now also there here "
    "project projects projcet meeting meetings discussed discuss issue issues team teams "
    "high low medium priority status about into from over under between still yet "
).split()) | set(_TYPE_WORDS) | _OPEN_WORDS


def _keywords(question: str) -> list[str]:
    """Specific content terms (names, 'vendor', 'api') after stripping noise + type/status words."""
    words = [normalize_name(w.strip(".,?!\"'")) for w in question.split()]
    return [w for w in words if w and w not in _STOP and len(w) > 2]


def nl_query(session: Session, question: str) -> dict:
    """Answer an English question, grounded in retrieved DB rows.

    Retrieval SCORES every record by:
      - +3 if the question names the record's entity TYPE (escalation/task/...)
      - +1 per question keyword found in the record's text
    Records with score > 0 are fed to the LLM, ranked best-first. Crucially,
    naming a type INCLUDES the record (keywords only re-rank, never exclude), so
    "action items from the new meeting" still returns tasks even when "new" matches
    nothing. All entity types AND meeting summaries are searched. If nothing scores,
    we hand the LLM a general org snapshot so it can still respond.
    """
    qwords = set(normalize_name(question).replace("?", " ").replace(".", " ").split())
    wanted = {_TYPE_WORDS[w] for w in qwords if w in _TYPE_WORDS}
    open_only = bool(qwords & _OPEN_WORDS)
    kw = _keywords(question)

    scored: list[tuple[int, dict, str | None]] = []

    def consider(rtype, status, fields, row, meeting_title):
        if open_only and status is not None and status != "open":
            return
        score = 3 if rtype in wanted else 0
        if kw:
            blob = " ".join(normalize_name(f) for f in fields if f)
            score += sum(1 for k in kw if k in blob)
        if score > 0:
            scored.append((score, row, meeting_title))

    for e in session.query(Escalation).all():
        mt = e.meeting.title if e.meeting else None
        consider("escalation", e.status,
                 [e.description, e.priority, e.status,
                  e.project.display_name if e.project else None,
                  e.raised_by.display_name if e.raised_by else None, mt],
                 {"type": "escalation", "description": e.description,
                  "raised_by": e.raised_by.display_name if e.raised_by else None,
                  "project": e.project.display_name if e.project else None,
                  "priority": e.priority, "severity": e.severity_score,
                  "status": e.status, "is_duplicate": bool(e.duplicate_of_id),
                  "meeting": mt}, mt)

    for t in session.query(Task).all():
        mt = t.meeting.title if t.meeting else None
        consider("task", t.status,
                 [t.description, t.priority, t.status, t.deadline,
                  t.project.display_name if t.project else None,
                  t.owner.display_name if t.owner else None, mt],
                 {"type": "task", "description": t.description,
                  "owner": t.owner.display_name if t.owner else None,
                  "project": t.project.display_name if t.project else None,
                  "deadline": t.deadline, "priority": t.priority,
                  "status": t.status, "meeting": mt}, mt)

    for r in session.query(Risk).all():
        mt = r.meeting.title if r.meeting else None
        consider("risk", None,
                 [r.description, r.impact, r.priority,
                  r.project.display_name if r.project else None, mt],
                 {"type": "risk", "description": r.description,
                  "project": r.project.display_name if r.project else None,
                  "impact": r.impact, "priority": r.priority,
                  "severity": r.severity_score, "meeting": mt}, mt)

    for b in session.query(Blocker).all():
        mt = b.meeting.title if b.meeting else None
        consider("blocker", b.status,
                 [b.description, b.status, b.project.display_name if b.project else None, mt],
                 {"type": "blocker", "description": b.description,
                  "project": b.project.display_name if b.project else None,
                  "status": b.status, "meeting": mt}, mt)

    for d in session.query(Decision).all():
        mt = d.meeting.title if d.meeting else None
        consider("decision", None,
                 [d.description, d.rationale, d.project.display_name if d.project else None, mt],
                 {"type": "decision", "description": d.description, "rationale": d.rationale,
                  "project": d.project.display_name if d.project else None, "meeting": mt}, mt)

    for q in session.query(OpenQuestion).all():
        mt = q.meeting.title if q.meeting else None
        consider("open_question", q.status,
                 [q.question, q.project.display_name if q.project else None, mt],
                 {"type": "open_question", "question": q.question,
                  "project": q.project.display_name if q.project else None, "meeting": mt}, mt)

    for f in session.query(FollowUp).all():
        mt = f.meeting.title if f.meeting else None
        consider("follow_up", None,
                 [f.description, f.owner.display_name if f.owner else None,
                  f.project.display_name if f.project else None, mt],
                 {"type": "follow_up", "description": f.description,
                  "owner": f.owner.display_name if f.owner else None,
                  "project": f.project.display_name if f.project else None, "meeting": mt}, mt)

    # The meetings themselves (title + summary) so meeting-level questions resolve.
    for m in session.query(Meeting).all():
        consider("meeting", None,
                 [m.title, m.summary, m.sentiment, m.urgency],
                 {"type": "meeting", "title": m.title, "summary": m.summary,
                  "sentiment": m.sentiment, "urgency": m.urgency}, m.title)

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:60]
    rows = [row for _, row, _ in top]
    sources = sorted({mt for _, _, mt in top if mt})

    # Fallback: nothing matched -> hand the LLM a general org snapshot so broad or
    # differently-worded questions still get a grounded answer.
    if not rows:
        snap = set()
        for m in session.query(Meeting).order_by(Meeting.id.desc()).limit(12).all():
            rows.append({"type": "meeting", "title": m.title, "summary": m.summary,
                         "sentiment": m.sentiment, "urgency": m.urgency})
            if m.title:
                snap.add(m.title)
        for e in session.query(Escalation).filter(Escalation.status == "open").all():
            mt = e.meeting.title if e.meeting else None
            rows.append({"type": "escalation", "description": e.description,
                         "project": e.project.display_name if e.project else None,
                         "severity": e.severity_score, "status": e.status, "meeting": mt})
            if mt:
                snap.add(mt)
        rows = rows[:60]
        sources = sorted(snap)

    if not rows:
        return {"answer": "There's no meeting data yet — ingest a meeting first.",
                "sources": []}

    answer = llm.answer_query(question, rows)
    return {"answer": answer, "sources": sources}


# ---------------- Relationship graph ----------------

def build_graph(session: Session) -> dict:
    """Nodes + edges for the relationship map (people, projects, escalations, tasks)."""
    nodes, edges = [], []
    seen = set()

    def add_node(nid, label, ntype):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "type": ntype})

    for p in session.query(Project).all():
        add_node(f"project:{p.id}", p.display_name or p.name, "project")
    for person in session.query(Person).all():
        add_node(f"person:{person.id}", person.display_name or person.name, "person")

    for t in session.query(Task).all():
        tid = f"task:{t.id}"
        add_node(tid, (t.description or "")[:40], "task")
        if t.owner:
            edges.append({"source": f"person:{t.owner.id}", "target": tid,
                          "label": "assigned_to"})
        if t.project:
            edges.append({"source": tid, "target": f"project:{t.project.id}",
                          "label": "belongs_to"})

    for e in session.query(Escalation).all():
        eid = f"esc:{e.id}"
        add_node(eid, (e.description or "")[:40], "escalation")
        if e.raised_by:
            edges.append({"source": eid, "target": f"person:{e.raised_by.id}",
                          "label": "raised_by"})
        if e.project:
            edges.append({"source": eid, "target": f"project:{e.project.id}",
                          "label": "affects"})

    return {"nodes": nodes, "edges": edges}
