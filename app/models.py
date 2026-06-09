"""ORM models — the structured schema the AI extraction is poured into.

Graph encoded as relational tables:
    Person  --assigned_to-->  Task          (Task.owner_id)
    Project --has_blocker-->  Blocker        (Blocker.project_id)
    Escalation --raised_by--> Person         (Escalation.raised_by_id)
    {Task, Escalation, Risk, Blocker, Decision} --belongs_to--> Project
    Meeting --contains--> every item          (item.meeting_id)
    Meeting <--participants--> Person         (meeting_participants link table)

People and Projects are deduplicated by a normalized name (see enrich.normalize_name),
so the same "Rahul" mentioned across many meetings is ONE row linked to all of them.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Table, JSON
)
from sqlalchemy.orm import relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Link table: which people attended / were mentioned in which meeting.
meeting_participants = Table(
    "meeting_participants",
    Base.metadata,
    Column("meeting_id", ForeignKey("meetings.id"), primary_key=True),
    Column("person_id", ForeignKey("people.id"), primary_key=True),
)


class Meeting(Base):
    __tablename__ = "meetings"
    id = Column(Integer, primary_key=True)
    title = Column(String, default="Untitled meeting")
    raw_text = Column(Text)
    source_type = Column(String, default="summary")  # summary | transcript | file
    summary = Column(Text)
    sentiment = Column(String)   # positive | neutral | negative | tense ...
    urgency = Column(String)     # low | medium | high
    created_at = Column(DateTime, default=_utcnow)

    participants = relationship("Person", secondary=meeting_participants,
                                back_populates="meetings")
    tasks = relationship("Task", back_populates="meeting")
    escalations = relationship("Escalation", back_populates="meeting")
    risks = relationship("Risk", back_populates="meeting")
    blockers = relationship("Blocker", back_populates="meeting")
    decisions = relationship("Decision", back_populates="meeting")


class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)  # stored normalized (lowercased)
    display_name = Column(String)                   # nicest-seen original casing
    team = Column(String)

    meetings = relationship("Meeting", secondary=meeting_participants,
                            back_populates="participants")
    owned_tasks = relationship("Task", back_populates="owner")
    raised_escalations = relationship("Escalation", back_populates="raised_by")


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True)  # normalized
    display_name = Column(String)
    status = Column(String, default="active")

    tasks = relationship("Task", back_populates="project")
    escalations = relationship("Escalation", back_populates="project")
    risks = relationship("Risk", back_populates="project")
    blockers = relationship("Blocker", back_populates="project")
    decisions = relationship("Decision", back_populates="project")


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    owner_id = Column(ForeignKey("people.id"))
    project_id = Column(ForeignKey("projects.id"))
    meeting_id = Column(ForeignKey("meetings.id"))
    deadline = Column(String)            # free-form ("Friday", "2026-06-13") — kept as-is
    status = Column(String, default="open")
    priority = Column(String)            # low | medium | high
    teams = Column(JSON, default=list)   # cross-team involvement

    owner = relationship("Person", back_populates="owned_tasks")
    project = relationship("Project", back_populates="tasks")
    meeting = relationship("Meeting", back_populates="tasks")


class Escalation(Base):
    __tablename__ = "escalations"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    raised_by_id = Column(ForeignKey("people.id"))
    project_id = Column(ForeignKey("projects.id"))
    meeting_id = Column(ForeignKey("meetings.id"))
    priority = Column(String)
    severity_score = Column(Integer, default=0)   # 0-100, computed by enrich.severity_score
    status = Column(String, default="open")
    teams = Column(JSON, default=list)
    duplicate_of_id = Column(ForeignKey("escalations.id"))  # set if a repeat of an earlier one
    created_at = Column(DateTime, default=_utcnow)

    raised_by = relationship("Person", back_populates="raised_escalations")
    project = relationship("Project", back_populates="escalations")
    meeting = relationship("Meeting", back_populates="escalations")
    duplicate_of = relationship("Escalation", remote_side=[id])


class Risk(Base):
    __tablename__ = "risks"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    project_id = Column(ForeignKey("projects.id"))
    meeting_id = Column(ForeignKey("meetings.id"))
    impact = Column(Text)
    priority = Column(String)
    severity_score = Column(Integer, default=0)

    project = relationship("Project", back_populates="risks")
    meeting = relationship("Meeting", back_populates="risks")


class Blocker(Base):
    __tablename__ = "blockers"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    project_id = Column(ForeignKey("projects.id"))
    meeting_id = Column(ForeignKey("meetings.id"))
    status = Column(String, default="open")

    project = relationship("Project", back_populates="blockers")
    meeting = relationship("Meeting", back_populates="blockers")


class Decision(Base):
    __tablename__ = "decisions"
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    rationale = Column(Text)
    project_id = Column(ForeignKey("projects.id"))
    meeting_id = Column(ForeignKey("meetings.id"))

    project = relationship("Project", back_populates="decisions")
    meeting = relationship("Meeting", back_populates="decisions")
