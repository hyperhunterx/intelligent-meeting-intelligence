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
_STOP = set("the a an of to in on for is are what which show list all me my our "
            "across this week current who whom whose and or with at by".split())


def _keywords(question: str) -> list[str]:
    words = [normalize_name(w.strip(".,?!\"'")) for w in question.split()]
    return [w for w in words if w and w not in _STOP and len(w) > 2]


def _row_matches(text_fields: list[str | None], keywords: list[str]) -> bool:
    blob = " ".join(normalize_name(f) for f in text_fields if f)
    return any(k in blob for k in keywords) if keywords else True


def nl_query(session: Session, question: str) -> dict:
    """Answer an English question, grounded in retrieved DB rows."""
    kw = _keywords(question)
    rows: list[dict] = []
    sources: set[str] = set()

    for e in session.query(Escalation).all():
        fields = [e.description, e.priority, e.status,
                  e.project.display_name if e.project else None,
                  e.raised_by.display_name if e.raised_by else None,
                  e.meeting.title if e.meeting else None]
        if _row_matches(fields, kw):
            rows.append({"type": "escalation", "description": e.description,
                         "raised_by": e.raised_by.display_name if e.raised_by else None,
                         "project": e.project.display_name if e.project else None,
                         "priority": e.priority, "severity": e.severity_score,
                         "status": e.status,
                         "meeting": e.meeting.title if e.meeting else None})
            if e.meeting:
                sources.add(e.meeting.title)

    for t in session.query(Task).all():
        fields = [t.description, t.priority, t.status, t.deadline,
                  t.project.display_name if t.project else None,
                  t.owner.display_name if t.owner else None,
                  t.meeting.title if t.meeting else None]
        if _row_matches(fields, kw):
            rows.append({"type": "task", "description": t.description,
                         "owner": t.owner.display_name if t.owner else None,
                         "project": t.project.display_name if t.project else None,
                         "deadline": t.deadline, "priority": t.priority,
                         "status": t.status,
                         "meeting": t.meeting.title if t.meeting else None})
            if t.meeting:
                sources.add(t.meeting.title)

    for r in session.query(Risk).all():
        fields = [r.description, r.impact, r.priority,
                  r.project.display_name if r.project else None,
                  r.meeting.title if r.meeting else None]
        if _row_matches(fields, kw):
            rows.append({"type": "risk", "description": r.description,
                         "project": r.project.display_name if r.project else None,
                         "impact": r.impact, "priority": r.priority,
                         "severity": r.severity_score,
                         "meeting": r.meeting.title if r.meeting else None})
            if r.meeting:
                sources.add(r.meeting.title)

    # Cap context size so we don't blow the prompt on big DBs.
    rows = rows[:40]
    if not rows:
        return {"answer": "I couldn't find any records matching that question.",
                "sources": []}

    answer = llm.answer_query(question, rows)
    return {"answer": answer, "sources": sorted(sources)}


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
