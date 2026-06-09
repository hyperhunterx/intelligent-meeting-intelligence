"""Tests for deterministic org-wide insight aggregations (written before impl).

We seed a fresh in-memory SQLite with known rows (no LLM involved) and assert the
aggregation math, so the leadership dashboard numbers can be trusted live.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Meeting, Person, Project, Task, Escalation, Risk
from app.queries import compute_insights


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    m1 = Meeting(title="Payments sync", urgency="high")
    m2 = Meeting(title="Platform review", urgency="medium")
    rahul = Person(name="rahul", display_name="Rahul")
    priya = Person(name="priya", display_name="Priya")
    pay = Project(name="payment integration", display_name="Payment Integration")
    plat = Project(name="platform", display_name="Platform")
    db.add_all([m1, m2, rahul, priya, pay, plat])
    db.flush()

    # 3 tasks: 2 owned by Rahul, 1 unowned (accountability gap).
    db.add_all([
        Task(description="Coordinate vendor fix", owner=rahul, project=pay,
             meeting=m1, priority="high", status="open"),
        Task(description="Write migration", owner=rahul, project=plat,
             meeting=m2, priority="medium", status="open"),
        Task(description="Unassigned cleanup", owner=None, project=plat,
             meeting=m2, priority="low", status="open"),
    ])
    # 2 escalations, one high severity, both open.
    db.add_all([
        Escalation(description="Vendor API unstable", raised_by=priya, project=pay,
                   meeting=m1, priority="high", severity_score=85, status="open"),
        Escalation(description="Flaky CI", raised_by=rahul, project=plat,
                   meeting=m2, priority="low", severity_score=30, status="open"),
    ])
    db.add(Risk(description="Phase-2 slip", project=pay, meeting=m1,
                priority="high", severity_score=70))
    db.commit()
    return db


def test_open_escalation_count(session):
    ins = compute_insights(session)
    assert ins["open_escalations"] == 2


def test_workload_counts_tasks_per_owner(session):
    ins = compute_insights(session)
    assert ins["workload"]["Rahul"] == 2


def test_accountability_gaps_flags_unowned_task(session):
    ins = compute_insights(session)
    assert ins["accountability_gaps"] >= 1


def test_project_health_present_for_each_project(session):
    ins = compute_insights(session)
    names = {p["project"] for p in ins["project_health"]}
    assert "Payment Integration" in names
    assert "Platform" in names


def test_top_risks_sorted_by_severity(session):
    ins = compute_insights(session)
    assert ins["top_risks"][0]["severity_score"] == 70
