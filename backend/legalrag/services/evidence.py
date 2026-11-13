"""Page images of the official Bulletin Officiel PDF for an article (what the user sees next to the quoted text)."""
from __future__ import annotations

import io
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ..config import Settings


class EvidenceError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status, self.msg = status, msg


def _from_uri(url: str | None) -> Path | None:
    if not url or not url.startswith("file:"):
        return None
    u = urlparse(url)
    p = url2pathname(unquote(u.path))
    if re.match(r"^[/\\][A-Za-z]:", p):  # file:///C:/x -> /C:/x on Windows
        p = p[1:]
    return Path(p)


def find_pdf(settings: Settings, url: str | None, bo_number: str | None) -> Path | None:
    p = _from_uri(url)
    if p and p.suffix.lower() == ".pdf" and p.exists():
        return p
    if bo_number:
        n = str(bo_number).strip().replace(" ", "-")
        names = {f"BO_{n}_Ar.pdf", f"BO_{n.replace('-bis', ' bis')}_Ar.pdf"}
        for d in (settings.resolved_bo_dir() / "pdfs", settings.resolved_bo_dir() / "frozen"):
            if d.exists():
                for f in d.rglob("*.pdf"):
                    if f.name in names:
                        return f
    return None


def page_count(pdf: Path) -> int | None:
    try:
        import pdfplumber

        with pdfplumber.open(pdf) as d:
            return len(d.pages)
    except Exception:  # noqa: BLE001
        return None


def render_page(pdf: Path, page: int, dpi: int = 110) -> bytes:
    """PNG of one page (1-based)."""
    try:
        import pdfplumber
    except ImportError:
        raise EvidenceError(501, "pdfplumber is not installed: pip install pdfplumber")
    with pdf.open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise EvidenceError(422, "not a PDF")
    with pdfplumber.open(pdf) as d:
        if not 1 <= page <= len(d.pages):
            raise EvidenceError(404, f"page {page} is outside the PDF ({len(d.pages)} pages)")
        im = d.pages[page - 1].to_image(resolution=dpi).original
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
