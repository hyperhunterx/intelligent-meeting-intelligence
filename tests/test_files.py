"""Tests for document text extraction (Gap 3: uploaded document files)."""
from pathlib import Path

from app.files import extract_text

SPEC_PDF = (Path(__file__).resolve().parent.parent
            / "Intelligent-Meeting-Intelligence-_-Escalation-Tracking-System.pdf")


def test_extract_plain_text():
    assert extract_text("notes.txt", b"Hello world") == "Hello world"


def test_extract_markdown_is_text():
    assert extract_text("notes.md", b"# Title\nbody") == "# Title\nbody"


def test_extract_handles_bad_bytes_gracefully():
    # Invalid UTF-8 shouldn't crash; it's decoded with errors ignored.
    assert isinstance(extract_text("x.txt", b"\xff\xfe bad"), str)


def test_extract_pdf_real_file():
    if not SPEC_PDF.exists():
        return  # skip if the sample PDF isn't present
    text = extract_text(SPEC_PDF.name, SPEC_PDF.read_bytes())
    assert "Meeting Intelligence" in text
    assert len(text) > 500
