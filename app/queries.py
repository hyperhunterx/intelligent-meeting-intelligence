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


def _row_matches(text_fields: list[str | None], keywords: list[str]) -> bool:
    blob = " ".join(normalize_name(f) for f in text_fields if f)
    return any(k in blob for k in keywords)


def nl_query(session: Session, question: str) -> dict:
    """Answer an English question, grounded in retrieved DB rows.

    Retrieval is TYPE-AWARE:
      - if the question names an entity type ("escalations", "tasks", "blockers"),
        we pull rows of that type wholesale (optionally filtered to open + keywords);
      - otherwise we pull any row whose text matches the specific keywords;
      - if nothing is specified at all, we fall back to open escalations + tasks.
    """
    qnorm = normalize_name(question)
    qwords = set(qnorm.replace("?", " ").replace(".", " ").split())
    wanted = {_TYPE_WORDS[w] for w in qwords if w in _TYPE_WORDS}
    open_only = bool(qwords & _OPEN_WORDS)
    kw = _keywords(question)

    rows: list[dict] = []
    sources: set[str] = set()

    def want(rtype: str, status: str | None, fields: list[str | None]) -> bool:
        """Decide if a row should be retrieved."""
        if open_only and status is not None and status != "open":
            return False
        type_hit = rtype in wanted
        kw_hit = _row_matches(fields, kw) if kw else False
        if wanted:
            # A type was requested: include rows of that type (further narrowed by
            # keywords if any were given), plus any strong keyword hit elsewhere.
            if type_hit:
                return _row_matches(fields, kw) if kw else True
            return kw_hit
        # No explicit type: pure keyword retrieval.
        return kw_hit

    def add_source(meeting_title):
        if meeting_title:
            sources.add(meeting_title)

    for e in session.query(Escalation).all():
        mt = e.meeting.title if e.meeting else None
        fields = [e.description, e.priority, e.status,
                  e.project.display_name if e.project else None,
                  e.raised_by.display_name if e.raised_by else None, mt]
        if want("escalation", e.status, fields):
            rows.append({"type": "escalation", "description": e.description,
                         "raised_by": e.raised_by.display_name if e.raised_by else None,
                         "project": e.project.display_name if e.project else None,
                         "priority": e.priority, "severity": e.severity_score,
                         "status": e.status, "is_duplicate": bool(e.duplicate_of_id),
                         "meeting": mt})
            add_source(mt)

    for t in session.query(Task).all():
        mt = t.meeting.title if t.meeting else None
        fields = [t.description, t.priority, t.status, t.deadline,
                  t.project.display_name if t.project else None,
                  t.owner.display_name if t.owner else None, mt]
        if want("task", t.status, fields):
            rows.append({"type": "task", "description": t.description,
                         "owner": t.owner.display_name if t.owner else None,
                         "project": t.project.display_name if t.project else None,
                         "deadline": t.deadline, "priority": t.priority,
                         "status": t.status, "meeting": mt})
            add_source(mt)

    for r in session.query(Risk).all():
        mt = r.meeting.title if r.meeting else None
        fields = [r.description, r.impact, r.priority,
                  r.project.display_name if r.project else None, mt]
        if want("risk", None, fields):
            rows.append({"type": "risk", "description": r.description,
                         "project": r.project.display_name if r.project else None,
                         "impact": r.impact, "priority": r.priority,
                         "severity": r.severity_score, "meeting": mt})
            add_source(mt)

    for b in session.query(Blocker).all():
        mt = b.meeting.title if b.meeting else None
        fields = [b.description, b.status,
                  b.project.display_name if b.project else None, mt]
        if want("blocker", b.status, fields):
            rows.append({"type": "blocker", "description": b.description,
                         "project": b.project.display_name if b.project else None,
                         "status": b.status, "meeting": mt})
            add_source(mt)

    # Fallback: nothing specified -> show the org's open hot-list.
    if not rows and not wanted and not kw:
        for e in session.query(Escalation).filter(Escalation.status == "open").all():
            mt = e.meeting.title if e.meeting else None
            rows.append({"type": "escalation", "description": e.description,
                         "raised_by": e.raised_by.display_name if e.raised_by else None,
                         "project": e.project.display_name if e.project else None,
                         "priority": e.priority, "severity": e.severity_score,
                         "status": e.status, "meeting": mt})
            add_source(mt)

    rows = rows[:40]  # cap context size
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
