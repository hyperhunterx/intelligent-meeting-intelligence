"""Deterministic enrichment — pure functions, no LLM, no DB.

This is the part of the system that must NEVER surprise us in a live demo, so
it's plain Python with unit tests. Three responsibilities:

1. normalize_name      -> entity resolution key (dedupe people/projects)
2. severity_score      -> bonus: numeric 0-100 risk/escalation prioritization
3. is_duplicate_escalation -> bonus: catch the same issue raised across meetings
"""
from difflib import SequenceMatcher


def normalize_name(s: str | None) -> str:
    """Canonical key for a person/project name: trimmed + lowercased.

    So "  Rahul ", "rahul", and "RAHUL" all collapse to one entity.
    """
    if not s:
        return ""
    return s.strip().lower()


# Priority -> base points. Unknown/None sits in the middle.
_PRIORITY_BASE = {"high": 60, "medium": 35, "low": 15}

# Words that signal real danger; each bumps the score.
_URGENT_KEYWORDS = (
    "critical", "outage", "down", "blocker", "blocked", "security", "breach",
    "data loss", "deadline", "urgent", "fail", "crash", "regression", "leak",
)


def severity_score(priority: str | None, is_escalation: bool, text: str | None) -> int:
    """Score 0-100 combining stated priority, escalation status, and danger words.

    - base from priority (high/medium/low)
    - +25 if it was raised as an escalation (someone pushed it up the chain)
    - +8 per urgent keyword found in the text
    Capped at 100.
    """
    score = _PRIORITY_BASE.get(normalize_name(priority), 25)
    if is_escalation:
        score += 25
    blob = (text or "").lower()
    for kw in _URGENT_KEYWORDS:
        if kw in blob:
            score += 8
    return max(0, min(100, score))


def is_duplicate_escalation(
    description: str,
    project: str | None,
    existing: list[dict],
    threshold: float = 0.6,
) -> bool:
    """True if `description` restates an existing escalation in the SAME project.

    Uses difflib ratio (no embeddings needed) on normalized text. Same project
    is required — identical words about different projects are different issues.
    Each item in `existing` is a dict with "description" and "project".
    """
    target_proj = normalize_name(project)
    target_desc = normalize_name(description)
    for item in existing:
        if normalize_name(item.get("project")) != target_proj:
            continue
        ratio = SequenceMatcher(None, target_desc,
                                normalize_name(item.get("description"))).ratio()
        if ratio >= threshold:
            return True
    return False
