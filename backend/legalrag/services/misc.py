"""Situation navigator, export with footnoted citations, error reports (reviewed by the user before sending)."""
from __future__ import annotations

import html
import io
import json
import uuid
from datetime import date
from typing import Any

from ..retrieval.engine import RetrievalRequest
from ..state import AppContext
from ..store.userdb import now
from ..verify import renderer

# situation id -> multilingual search phrases (retrieval only: the navigator quotes articles, it gives no advice)
SITUATIONS: dict[str, dict[str, Any]] = {
    "divorce": {"label": {"en": "Divorce", "fr": "Divorce", "ar": "الطلاق"}, "queries": ["divorce طلاق تطليق", "garde des enfants pension alimentaire النفقة الحضانة"]},
    "unpaid_wages": {"label": {"en": "Unpaid wages", "fr": "Salaires impayés", "ar": "أجور غير مؤداة"}, "queries": ["salaire paiement employeur الأجر المشغل", "salaire minimum SMIG الحد الأدنى للأجور"]},
    "rent": {"label": {"en": "Rent / lease", "fr": "Bail / loyer", "ar": "الكراء"}, "queries": ["bail loyer locataire الكراء المكتري", "expulsion éviction الإفراغ"]},
    "inheritance": {"label": {"en": "Inheritance", "fr": "Succession", "ar": "الإرث"}, "queries": ["succession héritiers الإرث الورثة التركة"]},
    "land_dispute": {"label": {"en": "Land or neighbour dispute", "fr": "Litige foncier ou de voisinage", "ar": "نزاع عقاري أو جوار"}, "queries": ["immatriculation foncière التحفيظ العقاري", "voisinage servitude الجوار الارتفاقات"]},
    "bounced_cheque": {"label": {"en": "Bounced cheque", "fr": "Chèque sans provision", "ar": "شيك بدون رصيد"}, "queries": ["chèque sans provision شيك بدون رصيد"]},
    "traffic_fine": {"label": {"en": "Traffic fine", "fr": "Amende de circulation", "ar": "مخالفة السير"}, "queries": ["amende infraction circulation مخالفة السير الغرامة"]},
}


def navigate(ctx: AppContext, situation: str, as_of: date | None, lang: str = "fr", limit: int = 5) -> dict[str, Any]:
    if situation not in SITUATIONS:
        raise KeyError(situation)
    when = as_of or ctx.today_fn()
    seen, out = set(), []
    for q in SITUATIONS[situation]["queries"]:
        res = ctx.engine.retrieve(RetrievalRequest(query=q, as_of=when, today=ctx.today_fn(), lang=lang, expand=False, keep=limit))
        for c in res.candidates:
            if c.chunk.provision_id not in seen and c.score > 0:
                seen.add(c.chunk.provision_id)
                out.append(renderer.source_entry(ctx.pack, c, lang, when, f"C{c.chunk.chunk_id}"))
    return {"situation": situation, "label": SITUATIONS[situation]["label"], "as_of": when.isoformat(), "articles": out[:limit], "notice": renderer.DISCLAIMER[renderer.L(lang)],
            "note": "Relevant articles are quoted from the law pack. No advice is given."}


# ---------------------------------------------------------------------------------------------------------- export
def render_export(ctx: AppContext, trace_id: str, fmt: str) -> tuple[bytes, str, str]:
    row = ctx.db.one("SELECT case_id FROM trace WHERE trace_id=?", (trace_id,))
    tr = ctx.db.get_trace(trace_id)
    if not tr or not row:
        raise KeyError(trace_id)
    restore = (lambda t: ctx.pseudo.restore(t, row["case_id"])[0]) if row["case_id"] else (lambda t: t)
    q = restore(tr.get("pseudonymised_question") or "")
    claims = tr.get("claims") or []
    sources = {s["id"]: s for s in (tr.get("sources_snapshot") or [])}
    order: list[str] = []
    for c in claims:
        for sid in c.get("sources", []):
            if sid not in order:
                order.append(sid)
    for sid in sources:
        if sid not in order:
            order.append(sid)
    num = {sid: i + 1 for i, sid in enumerate(order)}

    def foot(sid: str) -> str:
        s = sources.get(sid)
        if not s:
            return sid
        return (f"{s['law']}, {s['article']}, BO {s['bo'].get('number') or '?'} ({s['bo'].get('date') or '?'}); version valid {s['valid_from']} → {s['valid_to'] or 'present'}; "
                f"trust: {s['trust']}; source: {(s.get('source') or {}).get('url') or 'n/a'}")

    lines = [f"# Legal research note", "", f"**As-of date:** {tr.get('as_of')}  ", f"**Law pack:** {tr.get('pack_version')}  ", f"**Status:** {tr.get('status')}", ""]
    if q:
        lines += ["## Question", q, ""]
    lines += ["## Answer", ""]
    for c in claims:
        refs = "".join(f"[^{num[s]}]" for s in c.get("sources", []) if s in num)
        lines.append(f"- {restore(c['text'])}{refs}")
    if not claims:
        lines.append("_No model-written explanation: see the quoted articles._")
    lines += ["", "## Quoted law", ""]
    for sid in order:
        s = sources.get(sid)
        if s:
            lines += [f"**{s['law']}, {s['article']}** ({s['valid_from']} → {s['valid_to'] or 'present'}, {s['trust']})", "", f"> {s['text']}", ""]
    lines += [""] + [f"[^{n}]: {foot(sid)}" for sid, n in num.items()]
    lines += ["", f"---", renderer.DISCLAIMER["en"]]
    md = "\n".join(lines)
    if fmt == "md":
        return md.encode("utf-8"), "text/markdown; charset=utf-8", "note.md"
    if fmt == "html":
        body = "".join(f"<p>{html.escape(l)}</p>" for l in lines if l.strip())
        return f"<!doctype html><meta charset='utf-8'><body dir='auto'>{body}</body>".encode("utf-8"), "text/html; charset=utf-8", "note.html"
    import docx

    d = docx.Document()
    for l in lines:
        if l.startswith("# "):
            d.add_heading(l[2:], 0)
        elif l.startswith("## "):
            d.add_heading(l[3:], 1)
        elif l.strip():
            d.add_paragraph(l.lstrip("-> ").replace("**", ""))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "note.docx"


# -------------------------------------------------------------------------------------------------------- error reports
def create_error_report(ctx: AppContext, trace_id: str | None, what: str, correct_source: str) -> dict[str, Any]:
    tr = ctx.db.get_trace(trace_id) if trace_id else None
    case = (ctx.db.one("SELECT case_id FROM trace WHERE trace_id=?", (trace_id,)) or {"case_id": None})["case_id"] if trace_id else None
    # free-text comments are pseudonymised too: the report must contain no personal data by default
    comment = ctx.pseudo.pseudonymise(what, case or ctx.db.create_case()).text if what else ""
    report = {
        "report_id": uuid.uuid4().hex[:12], "created_at": now(), "pack_version": ctx.pack.version if ctx.pack else None,
        "question": (tr or {}).get("pseudonymised_question"), "as_of": (tr or {}).get("as_of"), "status": (tr or {}).get("status"),
        "answer_claims": [{"type": c.get("type"), "text": c.get("text"), "sources": c.get("sources")} for c in (tr or {}).get("claims") or []],
        "cited": [{"provision_id": r["provision_id"], "valid_from": r["valid_from"], "valid_to": r["valid_to"], "trust": r["trust"]} for r in (tr or {}).get("retrieved", [])],
        "model": (tr or {}).get("model"), "prompt_version": (tr or {}).get("prompt_version"),
        "user_comment": comment, "correct_source": correct_source,
    }
    # names restored in answer claims would be personal data: ensure placeholders only
    ctx.db.put_json("error_report", "id", report["report_id"], "payload_enc", report, created_at=now(), status="draft")
    ctx.db.log_gap("error report", None, None, report["as_of"], report["pack_version"], report["question"])
    return report


def submit_error_report(ctx: AppContext, report_id: str) -> dict[str, Any]:
    got = ctx.db.get_json("error_report", "id", report_id, "payload_enc")
    if not got:
        raise KeyError(report_id)
    report, row = got
    url = ctx.settings.report_endpoint
    if url:
        ctx.gateway.post_json(kind="error_report", provider="report-endpoint", model=None, url=url, headers={"content-type": "application/json"}, body=report,
                              user_fields=[report.get("question") or "", report.get("user_comment") or ""], case_id=None)
        status, where = "sent", url
    else:
        d = ctx.settings.data_dir / "reports"
        d.mkdir(exist_ok=True)
        p = d / f"error-report-{report_id}.json"
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        status, where = "saved_for_manual_sending", str(p)
    ctx.db.put_json("error_report", "id", report_id, "payload_enc", report, created_at=row["created_at"], status=status)
    return {"report_id": report_id, "status": status, "where": where}
