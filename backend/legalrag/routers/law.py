"""Law browsing and tools that need no language model: exact lookup, search, status card, time-travel, diff, wizard,
navigator, calculators, term finder, pack management, evaluation."""
from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ..calc.base import CalcError
from ..deps import get_ctx, require_pack, require_token
from ..retrieval.engine import RetrievalRequest
from ..schemas import CalcRequest, CompareIn, SearchIn, WizardIn
from ..services import evidence as ev
from ..services import misc, status as st
from ..services import terms as terms_svc
from ..state import AppContext, install_pack
from ..store.lawpack import LawPack, PackError
from ..text.citations import parse_citations
from ..verify import renderer

router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])


# ------------------------------------------------------------------------------------------------ pack management
@router.get("/pack", tags=["pack"])
def pack_info(ctx: AppContext = Depends(get_ctx)) -> dict:
    from .system import _pack

    return _pack(ctx)


def _pack_updater(ctx: AppContext):
    from ..pack_update import PackUpdater

    u = getattr(ctx, "pack_updater", None)
    if u is None:
        u = ctx.pack_updater = PackUpdater(ctx)  # type: ignore[attr-defined]
    return u


@router.get("/pack/update", tags=["pack"])
def pack_update_check(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Installed law pack vs the published one (reads pack_release.json online; downloads nothing)."""
    return _pack_updater(ctx).check()


@router.post("/pack/update", tags=["pack"], status_code=202)
def pack_update_start(ctx: AppContext = Depends(get_ctx)) -> dict:
    """Download, verify (SHA-256 + publisher signature) and install the published pack in the background."""
    from ..store.lawpack import PackError

    try:
        return _pack_updater(ctx).start()
    except PackError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/pack/update/progress", tags=["pack"])
def pack_update_progress(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"job": _pack_updater(ctx).job}


@router.post("/pack/update/cancel", tags=["pack"])
def pack_update_cancel(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"cancelling": _pack_updater(ctx).cancel()}


@router.get("/pack/coverage", tags=["pack"])
def pack_coverage(ctx: AppContext = Depends(require_pack)) -> dict:
    """Per instrument: SGG consolidated text exists?, official language editions, implementing-text status, article count."""
    return {"pack_version": ctx.pack.version, "instruments": ctx.pack.coverage(), "trust": ctx.pack.trust_stats(), "check_report": ctx.pack.meta.get("check_report")}


@router.post("/pack/import", tags=["pack"])
async def pack_import(pack: UploadFile = File(...), signature: UploadFile | None = File(None), ctx: AppContext = Depends(get_ctx)) -> dict:
    """Offline import / update of a signed law pack. The signature is verified before anything is replaced."""
    tmp = Path(tempfile.mkdtemp())
    p, s = tmp / "pack.db", tmp / "pack.db.sig"
    with open(p, "wb") as f:
        shutil.copyfileobj(pack.file, f)
    if signature:
        with open(s, "wb") as f:
            shutil.copyfileobj(signature.file, f)
    old_path = ctx.settings.resolved_lawpack_path()
    try:
        old = LawPack(old_path) if old_path.exists() else None
    except PackError:
        old = None
    try:
        res = install_pack(ctx, p, s if signature else None)
    except PackError as e:
        raise HTTPException(422, str(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    res["changes"] = st.pack_changes(ctx.pack, old) if ctx.pack else None
    if old:
        old.close()
    return res


@router.get("/pack/changes", tags=["pack"])
def pack_changes(ctx: AppContext = Depends(require_pack)) -> dict:
    """Articles that changed between the previous pack and this one (before-and-after notes)."""
    prev = ctx.settings.resolved_lawpack_path().with_name("previous.db")
    if not prev.exists():
        return {"previous_pack": None, "changes": []}
    old = LawPack(prev)
    try:
        return st.pack_changes(ctx.pack, old)
    finally:
        old.close()


# ------------------------------------------------------------------------------------------------ instruments & provisions
@router.get("/instruments", tags=["law"])
def instruments(kind: str | None = None, q: str | None = None, domain: str | None = None, ctx: AppContext = Depends(require_pack)) -> list[dict]:
    return ctx.pack.instruments(kind, q, domain)


@router.get("/instruments/{iid}", tags=["law"])
def instrument(iid: str, ctx: AppContext = Depends(require_pack)) -> dict:
    i = ctx.pack.instrument(iid)
    if not i:
        raise HTTPException(404)
    return {**i, "provision_count": len(ctx.pack.provisions_of(iid)), "aliases": [a for a, x in ctx.pack.aliases().items() if x == iid]}


@router.get("/instruments/{iid}/status", tags=["law"])
def law_status(iid: str, as_of: date | None = None, ctx: AppContext = Depends(require_pack)) -> dict:
    """Law status card: state computed from date ranges, transitional rules, contested flag, implementing-text status."""
    card = st.status_card(ctx.pack, iid, as_of or ctx.today_fn(), ctx.today_fn())
    if not card:
        raise HTTPException(404)
    return card


@router.get("/instruments/{iid}/provisions", tags=["law"])
def provisions(iid: str, ctx: AppContext = Depends(require_pack)) -> list[dict]:
    return ctx.pack.provisions_of(iid)


@router.get("/provisions/{pid}", tags=["law"])
def provision(pid: str, as_of: date | None = None, lang: str = "ar", ctx: AppContext = Depends(require_pack)) -> dict:
    """The article as in force on a date, Arabic and French side by side, with trust level and source link."""
    when = as_of or ctx.today_fn()
    ver = ctx.pack.version_at(pid, when)
    if not ver:
        p = ctx.pack.provision(pid)
        if not p:
            raise HTTPException(404, "unknown provision")
        raise HTTPException(404, {"code": "no_trusted_version_on_date", "as_of": when.isoformat(), "versions": [{k: v[k] for k in ("valid_from", "valid_to", "verification_status")} for v in ctx.pack.versions(pid)]})
    view = ctx.pack.provision_view(ver["pv_id"])
    inst = ctx.pack.instrument(view["instrument_id"])
    return {**view, "law": renderer.law_label(inst, lang), "as_of": when.isoformat(), "trust_note": renderer.TRUST_NOTE.get(view["verification_status"], ""), "pack": {"version": ctx.pack.version, "built_at": ctx.pack.built_at}}


def _evidence_pdf(ctx: AppContext, pid: str, as_of: date | None):
    when = as_of or ctx.today_fn()
    ver = ctx.pack.version_at(pid, when)
    if not ver:
        raise HTTPException(404, "no version of this article on that date")
    loc = ctx.pack.article_location(pid, ver["pv_id"])
    if not loc:
        raise HTTPException(404, "this pack does not record where the article sits in the PDF (rebuild it with the current version)")
    inst = ctx.pack.instrument(ctx.pack.provision_view(ver["pv_id"])["instrument_id"]) or {}
    pdf = ev.find_pdf(ctx.settings, loc.get("url"), inst.get("bo_number"))
    return loc, pdf, inst


@router.get("/provisions/{pid}/evidence", tags=["law"])
def provision_evidence(pid: str, as_of: date | None = None, ctx: AppContext = Depends(require_pack)) -> dict:
    """Where the article is in the official PDF: file name, pages, and whether the PDF is on this machine (page images)."""
    loc, pdf, inst = _evidence_pdf(ctx, pid, as_of)
    return {"provision_id": pid, "bo_number": inst.get("bo_number"), "bo_date": inst.get("bo_date"), "page_start": loc["page_start"], "page_end": loc["page_end"],
            "pdf_available": bool(pdf), "filename": pdf.name if pdf else None, "total_pages": ev.page_count(pdf) if pdf else None}


@router.get("/provisions/{pid}/page/{page}", tags=["law"], response_class=Response)
def provision_page_image(pid: str, page: int, as_of: date | None = None, dpi: int = 110, ctx: AppContext = Depends(require_pack)) -> Response:
    """PNG of one page of the official PDF, only pages that belong to this article (so the endpoint cannot be used to read the whole file)."""
    loc, pdf, _inst = _evidence_pdf(ctx, pid, as_of)
    if not pdf:
        raise HTTPException(404, "the PDF of this bulletin is not on this machine")
    if not loc["page_start"] <= page <= loc["page_end"]:
        raise HTTPException(403, f"page {page} is not part of this article (pages {loc['page_start']}-{loc['page_end']})")
    try:
        png = ev.render_page(pdf, page, max(60, min(dpi, 200)))
    except ev.EvidenceError as e:
        raise HTTPException(e.status, e.msg)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/provisions/{pid}/history", tags=["law"])
def history(pid: str, ctx: AppContext = Depends(require_pack)) -> dict:
    """Amendment trail: every version with its dates, amending law and trust level."""
    h = st.provision_history(ctx.pack, pid)
    if not h:
        raise HTTPException(404)
    return h


@router.post("/provisions/compare", tags=["law"])
def compare(body: CompareIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """Time-travel diff: the same article on two dates."""
    r = st.compare_dates(ctx.pack, body.provision_id, body.date_a, body.date_b, body.lang)
    if not r:
        raise HTTPException(404, "no version on either date")
    return r


@router.get("/provisions/{pid}/decisions", tags=["law"])
def provision_decisions(pid: str, ctx: AppContext = Depends(require_pack)) -> dict:
    """Court rulings applying this article. Interpretive support, shown separately from the statute."""
    return {"provision_id": pid, "decisions": ctx.pack.decisions_for(pid), "coverage_note": "Case-law coverage is selective and never complete."}


@router.get("/decisions", tags=["law"])
def search_decisions(q: str, ctx: AppContext = Depends(require_pack)) -> list[dict]:
    return ctx.pack.search_decisions(q)


@router.get("/decisions/{did}", tags=["law"])
def decision(did: str, ctx: AppContext = Depends(require_pack)) -> dict:
    d = ctx.pack.decision(did)
    if not d:
        raise HTTPException(404)
    return d


@router.get("/lookup", tags=["law"])
def lookup(ref: str, as_of: date | None = None, lang: str = "ar", ctx: AppContext = Depends(require_pack)) -> dict:
    """Exact citation lookup ("article 30 CPC", "الفصل 230 من ق.ل.ع"): plain lookup by ID, no search, no model."""
    when = as_of or ctx.today_fn()
    refs = parse_citations(ref, ctx.pack.aliases(), ctx.pack.instrument_ids())
    if not refs:
        raise HTTPException(422, "no article reference recognised")
    out = []
    for r in refs:
        if not r.instrument_id:
            out.append({"reference": r.raw, "error": "law_not_identified"})
            continue
        pid = ctx.pack.find_provision(r.instrument_id, r.number, r.suffix)
        ver = ctx.pack.version_at(pid, when) if pid else None
        if not ver:
            out.append({"reference": r.raw, "provision_id": pid, "error": "no_trusted_version_on_date" if pid else "article_not_in_pack",
                        "versions": [{"valid_from": v["valid_from"], "valid_to": v["valid_to"], "status": v["verification_status"]} for v in ctx.pack.versions(pid)] if pid else []})
            continue
        view = ctx.pack.provision_view(ver["pv_id"])
        out.append({"reference": r.raw, "provision": view, "law": renderer.law_label(ctx.pack.instrument(r.instrument_id), lang), "as_of": when.isoformat()})
    return {"results": out}


@router.post("/search", tags=["law"])
def search(body: SearchIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """Retrieval only (keyword + dense + rerank), no language model. Quoted articles with their trust levels."""
    when = body.as_of or ctx.today_fn()
    from ..pipeline.understand import understand

    u = understand(body.query, ctx.pack, today=ctx.today_fn(), explicit_as_of=when)
    res = ctx.engine.retrieve(RetrievalRequest(query=body.query, as_of=when, domains=u.domains, exact_refs=u.exact_refs, today=ctx.today_fn(), lang="ar" if u.lang == "darija" else u.lang,
                                               expand=body.expand, keep=body.limit, weak_device=bool(ctx.user_settings().get("weak_device"))))
    return {"as_of": when.isoformat(), "coverage": vars(res.coverage), "notes": res.notes, "modes_used": res.modes_used,
            "results": [renderer.source_entry(ctx.pack, c, u.lang, when, f"C{c.chunk.chunk_id}") for c in res.candidates]}


# ------------------------------------------------------------------------------------------------ wizard, navigator, terms, bills, concordance
@router.post("/wizard/which-rules-apply", tags=["wizard"])
def wizard(body: WizardIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """Asks filing / judgment dates, then shows the transitional rule text and both versions. It does not decide which applies."""
    return st.which_rules_apply(ctx.pack, body.instrument_id, body.filing_date, body.judgment_date, body.facts_date)


@router.get("/navigator", tags=["wizard"])
def navigator_list() -> list[dict]:
    return [{"id": k, "label": v["label"]} for k, v in misc.SITUATIONS.items()]


@router.get("/navigator/{situation}", tags=["wizard"])
def navigator(situation: str, as_of: date | None = None, lang: str = "fr", ctx: AppContext = Depends(require_pack)) -> dict:
    try:
        return misc.navigate(ctx, situation, as_of, lang)
    except KeyError:
        raise HTTPException(404, "unknown situation")


@router.get("/terms", tags=["law"])
def term_finder(q: str) -> list[dict]:
    """Everyday word (Arabic / French / Darija / English) -> the legal terms in each language."""
    return terms_svc.lookup(q)


@router.get("/pending-bills", tags=["law"])
def pending_bills(ctx: AppContext = Depends(require_pack)) -> dict:
    return {"bills": ctx.pack.pending_bills(), "note": "Pending bills are not law and are never used as an answer source."}


@router.get("/concordance", tags=["law"])
def concordance(old: str | None = None, new: str | None = None, ctx: AppContext = Depends(require_pack)) -> dict:
    """Old-versus-new article map (e.g. 1974 code to Law 58.25), labelled derived."""
    return {"label": "derived", "rows": ctx.pack.concordance(old, new)}


# ------------------------------------------------------------------------------------------------ calculators
@router.get("/calculators", tags=["calculators"])
def calculators(ctx: AppContext = Depends(require_pack)) -> list[dict]:
    return ctx.calcs.describe()


@router.post("/calculators/run", tags=["calculators"])
def run_calculator(body: CalcRequest, ctx: AppContext = Depends(require_pack)) -> dict:
    """Pure, tested functions with dated rate rows. Shows inputs, formula, legal basis and the table rows used. Fails closed."""
    try:
        return ctx.calcs.run(body.tool, body.inputs).to_dict()
    except CalcError as e:
        raise HTTPException(422 if e.status == "needs_input" else 409, {"status": e.status, "message": e.message, "missing": e.missing})


@router.get("/deadline-rules", tags=["calculators"])
def deadline_rules(ctx: AppContext = Depends(require_pack)) -> list[dict]:
    """Appeal and limitation rules held in the pack (case types, periods, trigger, applicability dates)."""
    return ctx.pack.all_deadline_rules()


@router.get("/rates", tags=["calculators"])
def rate_tables(ctx: AppContext = Depends(require_pack)) -> list[dict]:
    """Rate tables in the pack (key, kind, dated rows). Used by the tax calculator to offer only what the pack really holds."""
    out = []
    for k in ctx.pack.rate_keys():
        rows = ctx.pack.rate_rows(k)
        out.append({"key": k, "kind": "progressive" if any((r.get("extra") or {}).get("brackets") for r in rows) else "rate",
                    "rows": [{x: r.get(x) for x in ("value", "unit", "valid_from", "valid_to", "source_decree", "note")} for r in rows]})
    return out


# ------------------------------------------------------------------------------------------------ evaluation
@router.post("/eval/run", tags=["evaluation"])
def eval_run(ctx: AppContext = Depends(require_pack)) -> dict:
    """Runs the golden set generated from this pack against the live pipeline and reports the release gates."""
    from ..evalharness.golden import run_golden

    return run_golden(ctx)
