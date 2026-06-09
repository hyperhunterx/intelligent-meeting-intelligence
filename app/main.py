"""FastAPI application — the HTTP surface.

Routes:
  GET  /                      -> dashboard (HTML)
  POST /api/ingest            -> ingest meeting text  (the spec's required endpoint)
  POST /api/ingest/file       -> ingest an uploaded .txt/.md file
  POST /api/query             -> natural-language question -> grounded answer
  GET  /api/insights          -> org-wide aggregate intelligence
  GET  /api/graph             -> relationship nodes+edges
  POST /api/report            -> auto-generated action report (Markdown)
  GET  /api/meetings|escalations|tasks|projects -> list feeds for the dashboard
"""
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.db import init_db, get_session
from app.extraction import ingest_meeting
from app.queries import compute_insights, nl_query, build_graph
from app.reports import build_report
from app.schemas import IngestRequest, QueryRequest, QueryResponse, ReportRequest
from app.models import Meeting, Person, Project, Task, Escalation, Risk
from app.files import extract_text

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="IMIES — Intelligent Meeting Intelligence & Escalation Tracking")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def _startup():
    init_db()


# ---------------- UI ----------------

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------- Ingest ----------------

@app.post("/api/ingest")
def api_ingest(req: IngestRequest, db: Session = Depends(get_session)):
    """Ingest raw meeting text and return the extracted structured intelligence."""
    return ingest_meeting(db, req.text, title=req.title, source_type=req.source_type)


@app.post("/api/ingest/file")
async def api_ingest_file(file: UploadFile = File(...),
                          title: str | None = Form(None),
                          db: Session = Depends(get_session)):
    """Ingest an uploaded document in one shot — .txt, .md, .pdf, or .docx.

    (The dashboard instead uses /api/extract-text so the user can review the text
    before extracting, but this one-shot route stays for API/programmatic use.)
    """
    raw = extract_text(file.filename, await file.read())
    if not raw.strip():
        raise HTTPException(status_code=400,
                            detail="Could not extract any text from that file.")
    return ingest_meeting(db, raw, title=title or file.filename, source_type="file")


@app.post("/api/extract-text")
async def api_extract_text(file: UploadFile = File(...)):
    """Extract plain text from an uploaded document WITHOUT ingesting it.

    The dashboard calls this to load a file's text into the editor, so the user
    can review/edit before clicking "Extract intelligence".
    """
    raw = extract_text(file.filename, await file.read())
    if not raw.strip():
        raise HTTPException(status_code=400,
                            detail="Could not extract any text from that file.")
    return {"text": raw, "filename": file.filename}


# ---------------- Query / insights / graph / report ----------------

@app.post("/api/query", response_model=QueryResponse)
def api_query(req: QueryRequest, db: Session = Depends(get_session)):
    result = nl_query(db, req.question)
    return QueryResponse(**result)


@app.get("/api/insights")
def api_insights(db: Session = Depends(get_session)):
    return compute_insights(db)


@app.get("/api/graph")
def api_graph(db: Session = Depends(get_session)):
    return build_graph(db)


@app.post("/api/report")
def api_report(req: ReportRequest, db: Session = Depends(get_session)):
    return {"report": build_report(db, scope=req.scope, project=req.project)}


# ---------------- List feeds ----------------

@app.get("/api/meetings")
def api_meetings(db: Session = Depends(get_session)):
    return [{
        "id": m.id, "title": m.title, "source_type": m.source_type,
        "sentiment": m.sentiment, "urgency": m.urgency, "summary": m.summary,
        "created_at": m.created_at,
        "participants": [p.display_name or p.name for p in m.participants],
    } for m in db.query(Meeting).order_by(Meeting.id.desc()).all()]


@app.get("/api/meetings/{meeting_id}")
def api_meeting_detail(meeting_id: int, db: Session = Depends(get_session)):
    """Full meeting: the ORIGINAL raw transcript + everything extracted from it.

    This is the 'see the messy input next to the structured output' view.
    """
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {
        "id": m.id, "title": m.title, "source_type": m.source_type,
        "sentiment": m.sentiment, "urgency": m.urgency, "summary": m.summary,
        "created_at": m.created_at, "raw_text": m.raw_text,
        "participants": [p.display_name or p.name for p in m.participants],
        "escalations": [{"description": e.description, "priority": e.priority,
                         "severity_score": e.severity_score,
                         "raised_by": e.raised_by.display_name if e.raised_by else None,
                         "is_duplicate": bool(e.duplicate_of_id)} for e in m.escalations],
        "tasks": [{"description": t.description, "priority": t.priority,
                   "deadline": t.deadline,
                   "owner": t.owner.display_name if t.owner else None} for t in m.tasks],
        "risks": [{"description": r.description, "priority": r.priority,
                   "severity_score": r.severity_score} for r in m.risks],
        "blockers": [{"description": b.description, "status": b.status} for b in m.blockers],
        "decisions": [{"description": d.description, "rationale": d.rationale}
                      for d in m.decisions],
        "open_questions": [{"question": q.question, "status": q.status,
                            "project": q.project.display_name if q.project else None}
                           for q in m.open_questions],
        "follow_ups": [{"description": f.description,
                        "owner": f.owner.display_name if f.owner else None,
                        "project": f.project.display_name if f.project else None}
                       for f in m.follow_ups],
    }


@app.delete("/api/meetings/{meeting_id}")
def api_delete_meeting(meeting_id: int, db: Session = Depends(get_session)):
    """Delete a meeting and EVERYTHING extracted from it.

    Removes the meeting's tasks, escalations, risks, blockers, decisions and its
    participant links. People and projects are shared across meetings, so we only
    delete the ones that become orphaned (no longer referenced anywhere) — this
    keeps the knowledge graph tidy without breaking other meetings.
    """
    m = db.get(Meeting, meeting_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Meeting not found")

    title = m.title
    child_collections = (m.tasks, m.escalations, m.risks, m.blockers, m.decisions,
                         m.open_questions, m.follow_ups)
    counts = {"tasks": len(m.tasks), "escalations": len(m.escalations),
              "risks": len(m.risks), "blockers": len(m.blockers),
              "decisions": len(m.decisions),
              "open_questions": len(m.open_questions), "follow_ups": len(m.follow_ups)}

    # Other escalations may point to this meeting's escalations as duplicates —
    # null those references first so we don't leave a dangling foreign key.
    esc_ids = [e.id for e in m.escalations]
    if esc_ids:
        db.query(Escalation).filter(Escalation.duplicate_of_id.in_(esc_ids)).update(
            {Escalation.duplicate_of_id: None}, synchronize_session=False)

    # Remember the people/projects this meeting touched, to check for orphans after.
    people, projects = set(m.participants), set()
    for coll in child_collections:
        for x in coll:
            if getattr(x, "project", None):
                projects.add(x.project)
            if getattr(x, "owner", None):
                people.add(x.owner)
            if getattr(x, "raised_by", None):
                people.add(x.raised_by)

    # Delete the extracted items, then the participant links, then the meeting.
    for coll in child_collections:
        for x in list(coll):
            db.delete(x)
    m.participants.clear()
    db.delete(m)
    db.flush()

    # Orphan cleanup.
    removed_people = removed_projects = 0
    for p in people:
        db.refresh(p)
        if not p.meetings and not p.owned_tasks and not p.raised_escalations:
            db.delete(p)
            removed_people += 1
    for pr in projects:
        db.refresh(pr)
        if not (pr.tasks or pr.escalations or pr.risks or pr.blockers
                or pr.decisions or pr.open_questions or pr.follow_ups):
            db.delete(pr)
            removed_projects += 1
    db.commit()

    return {"deleted": True, "title": title, "removed": counts,
            "orphans_removed": {"people": removed_people, "projects": removed_projects}}


@app.get("/api/escalations")
def api_escalations(db: Session = Depends(get_session)):
    return [{
        "id": e.id, "description": e.description,
        "raised_by": e.raised_by.display_name if e.raised_by else None,
        "project": e.project.display_name if e.project else None,
        "priority": e.priority, "severity_score": e.severity_score,
        "status": e.status, "teams": e.teams,
        "is_duplicate": bool(e.duplicate_of_id),
        "meeting": e.meeting.title if e.meeting else None,
    } for e in db.query(Escalation).order_by(Escalation.severity_score.desc()).all()]


@app.get("/api/tasks")
def api_tasks(db: Session = Depends(get_session)):
    return [{
        "id": t.id, "description": t.description,
        "owner": t.owner.display_name if t.owner else None,
        "project": t.project.display_name if t.project else None,
        "deadline": t.deadline, "priority": t.priority, "status": t.status,
        "teams": t.teams, "meeting": t.meeting.title if t.meeting else None,
    } for t in db.query(Task).order_by(Task.id.desc()).all()]


@app.get("/api/projects")
def api_projects(db: Session = Depends(get_session)):
    return [{
        "id": p.id, "name": p.display_name or p.name, "status": p.status,
        "open_escalations": sum(1 for e in p.escalations if e.status == "open"),
        "open_tasks": sum(1 for t in p.tasks if t.status == "open"),
        "risks": len(p.risks),
    } for p in db.query(Project).all()]
