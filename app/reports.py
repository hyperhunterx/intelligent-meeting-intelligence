"""Auto-generated follow-up / action report (bonus feature).

Gathers the currently OPEN items (escalations, tasks, risks), groups them by
project, and asks the LLM to write a crisp leadership-ready Markdown report.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from app import llm
from app.models import Task, Escalation, Risk


def _collect_open_items(session: Session, project_filter: str | None = None) -> dict:
    grouped: dict[str, dict] = defaultdict(
        lambda: {"escalations": [], "tasks": [], "risks": []})

    for e in session.query(Escalation).filter(Escalation.status == "open").all():
        proj = e.project.display_name if e.project else "Unassigned"
        if project_filter and proj.lower() != project_filter.lower():
            continue
        grouped[proj]["escalations"].append({
            "description": e.description,
            "raised_by": e.raised_by.display_name if e.raised_by else None,
            "priority": e.priority, "severity": e.severity_score,
            "duplicate": bool(e.duplicate_of_id),
        })

    for t in session.query(Task).filter(Task.status == "open").all():
        proj = t.project.display_name if t.project else "Unassigned"
        if project_filter and proj.lower() != project_filter.lower():
            continue
        grouped[proj]["tasks"].append({
            "description": t.description,
            "owner": t.owner.display_name if t.owner else "UNASSIGNED",
            "deadline": t.deadline, "priority": t.priority,
        })

    for r in session.query(Risk).all():
        proj = r.project.display_name if r.project else "Unassigned"
        if project_filter and proj.lower() != project_filter.lower():
            continue
        grouped[proj]["risks"].append({
            "description": r.description, "impact": r.impact,
            "severity": r.severity_score,
        })

    return grouped


def build_report(session: Session, scope: str = "org",
                 project: str | None = None) -> str:
    """Return a Markdown action report for the org (or one project)."""
    project_filter = project if scope == "project" else None
    open_items = _collect_open_items(session, project_filter)
    if not open_items:
        return "## Action Report\n\nNo open items. Everything is on track. ✅"
    return llm.generate_report(dict(open_items))
