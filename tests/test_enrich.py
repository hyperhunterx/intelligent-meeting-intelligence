"""Tests for the deterministic enrichment logic (written before implementation).

These three functions are the demo-critical pure logic:
- normalize_name  -> entity resolution (one "Rahul" across meetings)
- severity_score  -> bonus: risk severity scoring
- is_duplicate_escalation -> bonus: duplicate escalation detection
"""
from app.enrich import normalize_name, severity_score, is_duplicate_escalation


def test_normalize_name_strips_and_lowercases():
    assert normalize_name("  Rahul ") == "rahul"
    assert normalize_name("Backend Team") == "backend team"
    assert normalize_name("PRIYA") == "priya"


def test_normalize_name_handles_none_and_empty():
    assert normalize_name(None) == ""
    assert normalize_name("") == ""


def test_severity_high_priority_escalation_scores_high():
    s = severity_score(priority="high", is_escalation=True,
                       text="critical outage blocker on production")
    assert s >= 70
    assert s <= 100


def test_severity_low_priority_note_scores_low():
    s = severity_score(priority="low", is_escalation=False, text="minor cosmetic note")
    assert s < 40


def test_severity_escalation_raises_score():
    base = severity_score(priority="medium", is_escalation=False, text="api issue")
    escalated = severity_score(priority="medium", is_escalation=True, text="api issue")
    assert escalated > base


def test_duplicate_detection_same_issue_same_project():
    existing = [{"description": "Vendor API is unstable", "project": "payment integration"}]
    assert is_duplicate_escalation(
        "Vendor API keeps being unstable", "Payment Integration", existing) is True


def test_duplicate_detection_different_issue_is_not_duplicate():
    existing = [{"description": "Vendor API is unstable", "project": "payment integration"}]
    assert is_duplicate_escalation(
        "Hiring pipeline is slow", "Recruiting", existing) is False


def test_duplicate_detection_same_text_different_project_is_not_duplicate():
    existing = [{"description": "Vendor API is unstable", "project": "payment integration"}]
    # Same words, but a different project => not the same escalation.
    assert is_duplicate_escalation(
        "Vendor API is unstable", "Analytics Revamp", existing) is False
