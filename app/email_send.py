"""Send the auto-generated action report by email (SMTP).

Self-contained: the app sends mail itself via SMTP (Gmail by default), configured
through .env. Degrades gracefully — if SMTP isn't configured it returns a clear
message instead of raising, so the dashboard can tell the user what to set.
"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


def _md_to_html(md: str) -> str:
    """Minimal Markdown -> HTML for the email body (headings, bold, bullets)."""
    out = []
    for line in (md or "").splitlines():
        s = line.rstrip()
        esc = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        import re
        esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
        if s.startswith("### "):
            out.append(f"<h3>{esc[4:]}</h3>")
        elif s.startswith("## "):
            out.append(f"<h2>{esc[3:]}</h2>")
        elif s.startswith("# "):
            out.append(f"<h2>{esc[2:]}</h2>")
        elif s.lstrip().startswith(("- ", "* ")):
            out.append(f"<li>{esc.lstrip()[2:]}</li>")
        elif not s.strip():
            out.append("<br>")
        else:
            out.append(f"<p>{esc}</p>")
    body = "\n".join(out)
    return (f"<div style='font-family:Arial,sans-serif;color:#1a1a1a;line-height:1.6;"
            f"max-width:640px'>{body}</div>")


def send_email(to: list[str], subject: str, markdown_body: str) -> dict:
    """Send an email. Returns {sent: bool, ...}. Never raises."""
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD):
        return {"sent": False,
                "error": "Email not configured. Set SMTP_USER and SMTP_PASSWORD in .env "
                         "(Gmail needs an App Password)."}
    if not to:
        return {"sent": False, "error": "No recipient email addresses provided."}

    sender = settings.SMTP_FROM or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    msg.attach(MIMEText(_md_to_html(markdown_body), "html", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(sender, to, msg.as_string())
        return {"sent": True, "recipients": to}
    except Exception as e:
        return {"sent": False, "error": f"SMTP error: {e}"}
