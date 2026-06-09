"""Tests for the SMTP email sender (no real network — SMTP is faked)."""
import app.email_send as em


class FakeSMTP:
    """Stand-in for smtplib.SMTP that records what would be sent."""
    last = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.tls = False; self.creds = None; self.sent = None
        FakeSMTP.last = self

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context=None): self.tls = True
    def login(self, user, password): self.creds = (user, password)
    def sendmail(self, sender, to, raw): self.sent = (sender, to, raw)


def test_not_configured(monkeypatch):
    monkeypatch.setattr(em.settings, "SMTP_USER", "")
    monkeypatch.setattr(em.settings, "SMTP_PASSWORD", "")
    r = em.send_email(["a@b.com"], "Subject", "body")
    assert r["sent"] is False
    assert "configured" in r["error"].lower()


def test_no_recipients(monkeypatch):
    monkeypatch.setattr(em.settings, "SMTP_USER", "me@gmail.com")
    monkeypatch.setattr(em.settings, "SMTP_PASSWORD", "app-pass")
    r = em.send_email([], "Subject", "body")
    assert r["sent"] is False
    assert "recipient" in r["error"].lower()


def test_sends_via_smtp(monkeypatch):
    monkeypatch.setattr(em.settings, "SMTP_USER", "me@gmail.com")
    monkeypatch.setattr(em.settings, "SMTP_PASSWORD", "app-pass")
    monkeypatch.setattr(em.settings, "SMTP_FROM", "")
    monkeypatch.setattr(em.smtplib, "SMTP", FakeSMTP)

    r = em.send_email(["a@b.com", "c@d.com"], "Action Report", "# Title\n- item one")
    assert r["sent"] is True
    assert r["recipients"] == ["a@b.com", "c@d.com"]

    sender, to, raw = FakeSMTP.last.sent
    assert sender == "me@gmail.com"
    assert to == ["a@b.com", "c@d.com"]
    assert "Action Report" in raw          # subject present
    assert FakeSMTP.last.tls is True        # STARTTLS used
    assert FakeSMTP.last.creds == ("me@gmail.com", "app-pass")


def test_md_to_html_basic():
    html = em._md_to_html("# Heading\n**bold** text\n- bullet")
    assert "<h2>Heading</h2>" in html
    assert "<b>bold</b>" in html
    assert "<li>bullet</li>" in html
