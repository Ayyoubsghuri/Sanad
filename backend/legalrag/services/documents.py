"""Uploaded documents: text extraction on the device, pseudonymisation, confidence gate, excerpt selection, notice reader.
The file itself never leaves the device; only pseudonymised excerpts the pipeline needs can be sent. Document content is untrusted input."""
from __future__ import annotations

import io
import re
import uuid
from datetime import date
from typing import Any

from ..retrieval.rerankers import LexicalReranker
from ..state import AppContext
from ..store.userdb import now
from ..text.citations import parse_citations
from ..text.dates import extract_dates


class UnsupportedDocument(Exception):
    pass


def extract_text(filename: str, content: bytes) -> str:
    name = filename.lower()
    if name.endswith((".txt", ".md", ".csv")):
        for enc in ("utf-8", "utf-16", "cp1256", "latin-1"):
            try:
                return content.decode(enc)
            except UnicodeDecodeError:
                continue
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        text = "\n\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages).strip()
        if not text:
            raise UnsupportedDocument("this PDF has no text layer (a scan); OCR is not available in this build, or install the 'ocr' extra")
        return text
    if name.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in d.paragraphs)
    if name.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        try:
            import pytesseract
            from PIL import Image

            return pytesseract.image_to_string(Image.open(io.BytesIO(content)), lang="ara+fra+eng")
        except ImportError as e:
            raise UnsupportedDocument("OCR engine not installed (install the 'ocr' extra and Tesseract with ara/fra data)") from e
    raise UnsupportedDocument(f"unsupported file type: {filename}")


def ingest(ctx: AppContext, filename: str, content: bytes, case_id: str) -> dict[str, Any]:
    text = extract_text(filename, content)
    ctx.db.create_case(case_id=case_id)
    keep_places = ctx.user_settings()["keep_places"]
    res = ctx.pseudo.pseudonymise(text, case_id, keep_places=keep_places, doc_like=True)
    status = "ready" if res.confidence >= ctx.settings.document_min_confidence else "review_required"
    doc_id = uuid.uuid4().hex[:12]
    ctx.db.put_json(
        "document", "doc_id", doc_id, "payload_enc",
        {"raw": text, "pseudo": res.text, "counts": res.counts, "warnings": res.warnings, "unknown": res.unknown_tokens},
        case_id=case_id, created_at=now(), filename=filename, status=status, confidence=res.confidence,
    )
    return {"doc_id": doc_id, "case_id": case_id, "status": status, "confidence": res.confidence, "entity_counts": res.counts, "warnings": res.warnings,
            "unknown_capitalised_words": res.unknown_tokens, "pseudonymised_preview": res.text[:3000], "chars": len(text),
            "next": "review the preview and mark missed names" if status == "review_required" else "ready to use"}


def _load(ctx: AppContext, doc_id: str):
    got = ctx.db.get_json("document", "doc_id", doc_id, "payload_enc")
    if not got:
        raise KeyError(doc_id)
    return got


def review(ctx: AppContext, doc_id: str, mark_terms: list[str], confirm: bool) -> dict[str, Any]:
    payload, row = _load(ctx, doc_id)
    for t in mark_terms:
        ctx.db.add_marked_term(t)
    res = ctx.pseudo.pseudonymise(payload["raw"], row["case_id"], keep_places=ctx.user_settings()["keep_places"], doc_like=True)
    status = "reviewed" if confirm else ("ready" if res.confidence >= ctx.settings.document_min_confidence else "review_required")
    payload.update(pseudo=res.text, counts=res.counts, warnings=res.warnings, unknown=res.unknown_tokens)
    ctx.db.put_json("document", "doc_id", doc_id, "payload_enc", payload, case_id=row["case_id"], created_at=row["created_at"], filename=row["filename"], status=status, confidence=res.confidence)
    return {"doc_id": doc_id, "status": status, "confidence": res.confidence, "entity_counts": res.counts, "warnings": res.warnings, "pseudonymised_preview": res.text[:3000]}


def get_pseudonymised(ctx: AppContext, doc_id: str) -> tuple[str, str]:
    payload, row = _load(ctx, doc_id)
    return payload["pseudo"], row["status"]


def excerpts(ctx: AppContext, doc_ids: list[str], question: str, k: int = 3, max_chars: int = 1200) -> list[str]:
    """Only the excerpts the pipeline needs (never the file), from documents that passed the confidence gate."""
    paras: list[str] = []
    for d in doc_ids:
        text, status = get_pseudonymised(ctx, d)
        if status not in ("ready", "reviewed"):
            raise PermissionError(f"document {d} needs review before any excerpt can be sent")
        paras += [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        return []
    scores = LexicalReranker().score(question, paras)
    top = sorted(zip(scores, paras), key=lambda x: -x[0])[:k]
    return [p[:max_chars] for s, p in top if s > 0]


def read_notice(ctx: AppContext, doc_id: str, as_of: date | None = None) -> dict[str, Any]:
    """Extract dates and cited articles from a notice / summons / contract / judgment and show the cited text. It does not judge the document."""
    payload, row = _load(ctx, doc_id)
    text = payload["raw"]
    dates = [{"date": d.date.isoformat(), "precision": d.precision, "raw": d.raw} for d in extract_dates(text)]
    cites: list[dict[str, Any]] = []
    if ctx.pack:
        for ref in parse_citations(text, ctx.pack.aliases(), ctx.pack.instrument_ids()):
            pid = ctx.pack.find_provision(ref.instrument_id, ref.number, ref.suffix) if ref.instrument_id else None
            when = as_of or ctx.today_fn()
            ver = ctx.pack.version_at(pid, when) if pid else None
            cites.append({"reference": ref.raw, "instrument_id": ref.instrument_id, "provision_id": pid,
                          "text": ctx.pack.texts(ver["pv_id"]) if ver else None, "version": ver and {"valid_from": ver["valid_from"], "valid_to": ver["valid_to"], "trust": ver["verification_status"]}})
    parties = sorted(set(re.findall(r"\[(?:PERSON|ORG)_\d+\]", payload["pseudo"])))
    return {"doc_id": doc_id, "dates": dates, "cited_provisions": cites, "parties_as_placeholders": parties,
            "notice": "Extraction only: the app does not assess the document. Consult a legal professional about its content."}
