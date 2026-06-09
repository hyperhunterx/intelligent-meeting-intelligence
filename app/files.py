"""Extract plain text from an uploaded document.

Supports the document formats a meeting might arrive as:
  - .pdf            -> pypdf
  - .docx           -> python-docx
  - .txt / .md / *  -> decoded as UTF-8 text (default)

Kept as a pure function (filename + bytes -> text) so it is easy to unit-test.
"""
from io import BytesIO


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()

    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()

    if name.endswith(".docx"):
        import docx
        document = docx.Document(BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs).strip()

    # Default: treat as plain text (.txt, .md, or unknown).
    return data.decode("utf-8", errors="ignore").strip()
