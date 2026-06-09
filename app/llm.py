"""LLM client — the GenAI layer, via OpenRouter (OpenAI-compatible API).

The model is used for exactly two reasoning jobs plus one writing job:
  - extract_meeting()  : messy text  -> structured JSON (validated)
  - answer_query()     : question + retrieved rows -> grounded English answer
  - generate_report()  : open items -> a follow-up/action report

OpenRouter speaks the OpenAI protocol, so we use the `openai` SDK and just point
its base_url at OpenRouter. Swapping models = changing MODEL in .env, nothing else.
"""
import json

from openai import OpenAI

from app.config import settings
from app.schemas import MeetingExtraction

client = OpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
)

# A compact JSON shape description handed to the model so it knows the contract.
_EXTRACTION_SHAPE = """{
  "title": str, "summary": str,
  "sentiment": "positive|neutral|negative|tense",
  "urgency": "low|medium|high",
  "projects": [str], "people": [str],
  "tasks": [{"description": str, "owner": str, "deadline": str, "priority": "low|medium|high", "project": str, "teams": [str]}],
  "escalations": [{"description": str, "raised_by": str, "project": str, "priority": "low|medium|high", "teams": [str]}],
  "risks": [{"description": str, "project": str, "impact": str, "priority": "low|medium|high"}],
  "blockers": [{"description": str, "project": str, "status": str}],
  "decisions": [{"description": str, "rationale": str, "project": str}],
  "open_questions": [{"question": str, "project": str}],
  "follow_ups": [{"description": str, "owner": str, "project": str}]
}"""

_EXTRACT_SYSTEM = (
    "You are an organizational intelligence engine. You read raw meeting content "
    "(summaries, transcripts, or chat) and extract structured intelligence: projects, "
    "people, action items with owners and deadlines, escalations and who raised them, "
    "risks, blockers, key decisions, OPEN QUESTIONS (unresolved questions raised but not "
    "answered), and FOLLOW-UPS (next steps / follow-up actions). Infer priority and urgency from tone. "
    "Use the person's name as written. Only include items actually supported by the text "
    "(do not invent). Respond with ONLY a JSON object matching this shape:\n"
    + _EXTRACTION_SHAPE
)


def _chat_json(system: str, user: str) -> dict:
    """Call the model and parse its JSON reply. Raises on bad JSON."""
    resp = client.chat.completions.create(
        model=settings.MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def extract_meeting(text: str) -> MeetingExtraction:
    """Extract structured intelligence from one meeting's raw text.

    Strategy: try once; if JSON/validation fails, retry once with a stricter nudge;
    if it still fails, return a minimal valid object so ingestion never crashes.
    """
    user = f"Extract the intelligence from this meeting content:\n\n{text}"
    for attempt in range(2):
        try:
            data = _chat_json(_EXTRACT_SYSTEM, user)
            return MeetingExtraction.model_validate(data)
        except Exception:
            user = (
                "Your previous response was not valid JSON for the required schema. "
                "Return ONLY a single valid JSON object, no prose, no markdown fences.\n\n"
                f"Meeting content:\n{text}"
            )
    # Graceful degradation — keep the system alive even if the model misbehaves.
    return MeetingExtraction(summary=text[:300], urgency="medium")


_QUERY_SYSTEM = (
    "You are an analyst answering questions about an organization's meetings. "
    "You are given the user's question and a JSON list of RELEVANT RECORDS pulled "
    "from the database (escalations, tasks, risks, projects, meetings). "
    "Answer ONLY from these records — do not invent facts. Be concise and specific "
    "(names, projects, deadlines, statuses). If the records don't contain the answer, "
    "say so. Mention the meeting titles you drew from."
)


def answer_query(question: str, context_rows: list[dict]) -> str:
    """Answer an English question grounded in retrieved DB rows."""
    user = (
        f"QUESTION: {question}\n\n"
        f"RELEVANT RECORDS (JSON):\n{json.dumps(context_rows, default=str, indent=2)}"
    )
    resp = client.chat.completions.create(
        model=settings.MODEL,
        messages=[{"role": "system", "content": _QUERY_SYSTEM},
                  {"role": "user", "content": user}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


_REPORT_SYSTEM = (
    "You are a chief-of-staff writing a crisp follow-up action report for leadership. "
    "Given a JSON list of OPEN ITEMS (escalations, tasks, risks) grouped by project, "
    "produce a short, well-structured Markdown report: a one-line health summary, then "
    "per-project sections listing owners, deadlines, escalations (with severity), and "
    "recommended next steps. Be direct and actionable. Use only the provided data."
)


def generate_report(open_items: dict) -> str:
    """Generate a Markdown follow-up/action report from open items."""
    user = f"OPEN ITEMS (JSON):\n{json.dumps(open_items, default=str, indent=2)}"
    resp = client.chat.completions.create(
        model=settings.MODEL,
        messages=[{"role": "system", "content": _REPORT_SYSTEM},
                  {"role": "user", "content": user}],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()
