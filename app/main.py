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

from fastapi import FastAPI, Depends, UploadFile, File, Form
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
    """Ingest an uploaded text document (.txt/.md)."""
    raw = (await file.read()).decode("utf-8", errors="ignore")
    return ingest_meeting(db, raw, title=title or file.filename, source_type="file")


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
