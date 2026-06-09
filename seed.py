"""Seed the database with sample meetings so the dashboard is alive on first run.

Usage:
    python seed.py            # ingest all sample meetings
    python seed.py --reset    # delete imies.db first, then ingest

Each meeting goes through the REAL ingestion pipeline (LLM extraction + enrichment),
so this also doubles as a smoke test of the whole backend. Requires a valid
OPENROUTER_API_KEY in .env.
"""
import json
import os
import sys
from pathlib import Path

from app.config import settings
from app.db import init_db, SessionLocal
from app.extraction import ingest_meeting

DATA = Path(__file__).parent / "data" / "sample_meetings.json"


def main():
    if "--reset" in sys.argv and os.path.exists(settings.DB_PATH):
        os.remove(settings.DB_PATH)
        print(f"Removed existing {settings.DB_PATH}")

    init_db()
    meetings = json.loads(DATA.read_text(encoding="utf-8"))
    session = SessionLocal()
    try:
        for m in meetings:
            print(f"Ingesting: {m['title']} ...", flush=True)
            result = ingest_meeting(session, m["text"], title=m["title"],
                                    source_type=m.get("source_type", "summary"))
            c = result["counts"]
            print(f"   -> {c['escalations']} escalations, {c['tasks']} tasks, "
                  f"{c['risks']} risks, {c['decisions']} decisions "
                  f"(sentiment: {result['sentiment']}, urgency: {result['urgency']})")
    finally:
        session.close()
    print("\nSeed complete. Run:  uvicorn app.main:app --reload   then open http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
