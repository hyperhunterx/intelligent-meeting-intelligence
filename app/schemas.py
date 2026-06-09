"""Pydantic schemas.

Two jobs:
1. EXTRACTION CONTRACT — the exact JSON shape we force the LLM to return when
   it reads a meeting. Pydantic validates it, so downstream code can trust the
   structure (no "did the model include this key?" guessing).
2. API I/O — request/response bodies for the FastAPI endpoints.

The extraction shape mirrors the PDF's "Expected AI Output"
(Project / Blocker / Owner / Deadline / Risk / Escalation-by / Teams / Priority).
"""
from typing import Optional
from pydantic import BaseModel, Field


# ---------- Extraction contract (LLM output) ----------

class ExtractedTask(BaseModel):
    description: str
    owner: Optional[str] = None
    deadline: Optional[str] = None
    priority: Optional[str] = None        # low | medium | high
    project: Optional[str] = None
    teams: list[str] = Field(default_factory=list)


class ExtractedEscalation(BaseModel):
    description: str
    raised_by: Optional[str] = None
    project: Optional[str] = None
    priority: Optional[str] = None
    teams: list[str] = Field(default_factory=list)


class ExtractedRisk(BaseModel):
    description: str
    project: Optional[str] = None
    impact: Optional[str] = None
    priority: Optional[str] = None


class ExtractedBlocker(BaseModel):
    description: str
    project: Optional[str] = None
    status: Optional[str] = None


class ExtractedDecision(BaseModel):
    description: str
    rationale: Optional[str] = None
    project: Optional[str] = None


class MeetingExtraction(BaseModel):
    """The complete structured intelligence pulled from one meeting."""
    title: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None        # positive | neutral | negative | tense
    urgency: Optional[str] = None          # low | medium | high
    projects: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    tasks: list[ExtractedTask] = Field(default_factory=list)
    escalations: list[ExtractedEscalation] = Field(default_factory=list)
    risks: list[ExtractedRisk] = Field(default_factory=list)
    blockers: list[ExtractedBlocker] = Field(default_factory=list)
    decisions: list[ExtractedDecision] = Field(default_factory=list)


# ---------- API request/response models ----------

class IngestRequest(BaseModel):
    text: str
    title: Optional[str] = None
    source_type: str = "summary"


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


class ReportRequest(BaseModel):
    scope: str = "org"          # "org" or "project"
    project: Optional[str] = None
