"""Database wiring (SQLAlchemy + SQLite).

We use SQLite because it needs zero setup — the whole "organizational memory"
lives in a single file (`imies.db`). SQLAlchemy gives us Python classes that
map to tables, so we write Python instead of raw SQL for writes, and clean
SQL-like queries for reads.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

# `check_same_thread=False` lets FastAPI's threadpool share the connection.
engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Every ORM model inherits from this Base so SQLAlchemy can track the schema.
Base = declarative_base()


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    import app.models  # noqa: F401  (import registers the models on Base)
    Base.metadata.create_all(bind=engine)


def get_session():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
