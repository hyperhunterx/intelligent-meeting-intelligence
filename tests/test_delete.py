"""Delete-meeting orphan cleanup, incl. the 'bare project' case (regression)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Meeting, Person, Project, Task
from app.main import api_delete_meeting


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_delete_removes_bare_item_less_project(db):
    """A project created with NO items must be swept when the meeting is deleted."""
    m = Meeting(title="M")
    bare = Project(name="phase-2", display_name="Phase-2")   # no tasks/escalations/etc.
    linked = Project(name="phase-2 release", display_name="Phase-2 release")
    rahul = Person(name="rahul", display_name="Rahul")
    db.add_all([m, bare, linked, rahul]); db.flush()
    db.add(Task(description="ship it", owner=rahul, project=linked, meeting=m))
    db.commit()
    assert db.query(Project).count() == 2

    api_delete_meeting(m.id, db)

    # Both the linked and the bare project are now orphaned -> all gone.
    assert db.query(Meeting).count() == 0
    assert db.query(Project).count() == 0
    assert db.query(Person).count() == 0


def test_delete_keeps_project_used_by_another_meeting(db):
    m1, m2 = Meeting(title="M1"), Meeting(title="M2")
    proj = Project(name="payments", display_name="Payments")
    p = Person(name="sam", display_name="Sam")
    db.add_all([m1, m2, proj, p]); db.flush()
    db.add(Task(description="a", owner=p, project=proj, meeting=m1))
    db.add(Task(description="b", owner=p, project=proj, meeting=m2))
    db.commit()

    api_delete_meeting(m1.id, db)

    # proj + person still referenced by m2 -> kept.
    assert db.query(Project).count() == 1
    assert db.query(Person).count() == 1
    assert db.query(Meeting).count() == 1
