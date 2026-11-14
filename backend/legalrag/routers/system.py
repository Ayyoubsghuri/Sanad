"""Health, settings, secrets, cases + vault, pseudonymiser preview, outbound log, traces, saved searches, gaps, error reports, export, reminders."""
from __future__ import annotations

import json
import uuid
from datetime import date

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..calc.base import CalcError
from ..deps import get_ctx, require_pack, require_token
from ..schemas import ErrorReportIn, ExportIn, MarkTermIn, PseudoIn, ReminderIn, SavedSearchIn, SecretIn, SettingsUpdate
from ..services import misc
from ..state import AppContext
from ..store.userdb import now

public = APIRouter()
router = APIRouter(prefix="/v1", dependencies=[Depends(require_token)])

SECRET_NAMES = {"llm_main", "llm_claim_check", "embedder_cloud", "reranker_cloud"}


@public.get("/health", tags=["system"])
def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"status": "ok", "pack_loaded": ctx.pack is not None, "pack_usable": ctx.pack_usable(), "pack_error": ctx.pack_error}


_LOOPBACK_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


@public.post("/pair", tags=["system"])
def pair(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Automatic first-run pairing: the app (a local origin) fetches the API token itself, so the user never copies it.

    Only answers requests whose Origin is the desktop shell / a loopback dev server. A web page from any other site is refused,
    and the custom header below forces a CORS preflight, which those sites also fail. Host is already pinned to loopback."""
    origin = request.headers.get("origin", "")
    allowed = origin in ctx.settings.allowed_origins or bool(_LOOPBACK_ORIGIN.match(origin))
    if not origin or not allowed or request.headers.get("x-legalrag-pair") != "1":
        raise HTTPException(403, "pairing is only available to the local app")
    return {"token": ctx.api_token}


@router.get("/status", tags=["system"])
def status(ctx: AppContext = Depends(get_ctx)) -> dict:
    llm = ctx.llm()
    return {
        "mode": ctx.mode, "settings": ctx.user_settings(), "pack": _pack(ctx), "key_storage": ctx.keys.storage,
        "providers": {"llm": {"provider": llm.name, "model": llm.model} if llm else None, "claim_checker": ctx.claim_checker().name,
                      "embedder": getattr(ctx.embedder(), "embedder_id", None), "embedder_location": getattr(ctx.embedder(), "location", None),
                      "reranker": getattr(ctx.reranker(), "name", None), "reranker_location": getattr(ctx.reranker(), "location", None), "reranker_error": ctx.reranker_error},
        "secrets_configured": {n: ctx.keys.has_secret(n) for n in sorted(SECRET_NAMES)},
        "calculators": ctx.calcs.status if ctx.calcs else None,
        "arabic_ner": ctx.pseudo.ner.status if ctx.pseudo.ner else None,
    }


def _pack(ctx: AppContext) -> dict:
    if not ctx.pack:
        return {"loaded": False, "error": ctx.pack_error}
    age = ctx.pack_age_days()
    return {"loaded": True, "usable": ctx.pack_usable(), "version": ctx.pack.version, "built_at": ctx.pack.built_at, "age_days": age,
            "stale": bool(age is not None and age > ctx.settings.pack_max_age_days), "signature": ctx.pack_trust.state if ctx.pack_trust else None,
            "embedders": list(ctx.pack.embedders()), "trust": ctx.pack.trust_stats(), "last_bo_check": ctx.pack.meta.get("last_bo_check"), "error": ctx.pack_error}


# ------------------------------------------------------------------------------------------------ settings & secrets
@router.get("/settings", tags=["settings"])
def get_settings(ctx: AppContext = Depends(get_ctx)) -> dict:
    return ctx.user_settings()


@router.patch("/settings", tags=["settings"])
def update_settings(body: SettingsUpdate, ctx: AppContext = Depends(get_ctx)) -> dict:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("mode") == "cloud_assisted":  # disabled in this version
        changes["mode"] = "hybrid"
    return ctx.db.set_settings(changes)


@router.put("/secrets/{name}", tags=["settings"], status_code=204)
def put_secret(name: str, body: SecretIn, ctx: AppContext = Depends(get_ctx)) -> Response:
    """Store an API key in the OS keychain (never returned by any endpoint, never embedded in the app)."""
    if name not in SECRET_NAMES:
        raise HTTPException(404, f"unknown secret; allowed: {sorted(SECRET_NAMES)}")
    ctx.keys.set_secret(name, body.value)
    return Response(status_code=204)


@router.delete("/secrets/{name}", tags=["settings"], status_code=204)
def delete_secret(name: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    if name not in SECRET_NAMES:
        raise HTTPException(404)
    ctx.keys.delete_secret(name)
    return Response(status_code=204)


@router.post("/benchmark", tags=["settings"])
def run_benchmark(ctx: AppContext = Depends(require_pack)) -> dict:
    """Short first-launch benchmark: times the local embedder and reranker and suggests a mode."""
    import time

    from ..retrieval.engine import RetrievalRequest

    t0 = time.monotonic()
    emb = ctx.embedder()
    emb.embed(["benchmark question about dismissal and notice"] * 3)
    t_emb = (time.monotonic() - t0) / 3
    t1 = time.monotonic()
    rr = ctx.reranker()
    rr.score("benchmark", ["passage one about dismissal", "passage two about notice"] * 15)
    t_rr = time.monotonic() - t1
    weak = t_emb > 1.5 or t_rr > 4.0
    result = {"embed_s_per_query": round(t_emb, 3), "rerank_30_pairs_s": round(t_rr, 3), "weak_device": weak, "suggested_mode": "hybrid"}
    ctx.db.set_settings({"benchmark": result, "weak_device": weak})
    return result


# ------------------------------------------------------------------------------------------------ cases, vault, pseudonymiser
@router.get("/cases", tags=["privacy"])
def list_cases(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return ctx.db.list_cases()


@router.post("/cases", tags=["privacy"], status_code=201)
def create_case(label: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"case_id": ctx.db.create_case(label)}


@router.delete("/cases/{case_id}", tags=["privacy"], status_code=204)
def delete_case(case_id: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    """Wipes the vault mapping, documents, traces and logs for the case."""
    ctx.db.delete_case(case_id)
    return Response(status_code=204)


@router.get("/cases/{case_id}/vault", tags=["privacy"])
def vault_overview(case_id: str, reveal: bool = False, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Placeholders held for a case. Originals are shown only on explicit request and never leave the device."""
    items = ctx.db.vault_all(case_id)
    return {"case_id": case_id, "entries": [{"placeholder": p, "kind": k, **({"original": o} if reveal else {})} for p, (k, o) in sorted(items.items())]}


@router.post("/pseudonymise/preview", tags=["privacy"])
def pseudonymise_preview(body: PseudoIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    case_id = ctx.db.create_case(case_id=body.case_id) if body.case_id else ctx.db.create_case()
    keep = ctx.user_settings()["keep_places"] if body.keep_places is None else body.keep_places
    r = ctx.pseudo.pseudonymise(body.text, case_id, keep_places=keep, extra_terms=[(t, "PERSON") for t in body.extra_sensitive_terms])
    return {"case_id": case_id, "text": r.text, "confidence": r.confidence, "warnings": r.warnings, "unknown_capitalised_words": r.unknown_tokens, "entity_counts": r.counts,
            "highlights": [{"placeholder": e.placeholder, "kind": e.kind, "start": e.start, "end": e.end} for e in r.entities]}


@router.get("/marked-terms", tags=["privacy"])
def marked_terms(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"count": len(ctx.db.marked_terms())}


@router.post("/marked-terms", tags=["privacy"], status_code=201)
def mark_term(body: MarkTermIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """User marks a name the detector missed; remembered for all future texts."""
    ctx.db.add_marked_term(body.term, body.kind)
    return {"ok": True}


@router.delete("/marked-terms", tags=["privacy"], status_code=204)
def clear_marked_terms(ctx: AppContext = Depends(get_ctx)) -> Response:
    ctx.db.remove_marked_terms()
    return Response(status_code=204)


# ------------------------------------------------------------------------------------------------ outbound log, traces, history
@router.get("/outbound-log", tags=["privacy"])
def outbound_log(limit: int = 100, ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    """The exact pseudonymised payloads that left (or were blocked from leaving) the device."""
    return ctx.db.list_outbound(limit)


@router.delete("/outbound-log", tags=["privacy"])
def clear_outbound_log(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"deleted": ctx.db.clear_outbound()}


@router.get("/traces", tags=["history"])
def list_traces(limit: int = 50, ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return ctx.db.list_traces(limit)


@router.get("/traces/{trace_id}", tags=["history"])
def get_trace(trace_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    t = ctx.db.get_trace(trace_id)
    if not t:
        raise HTTPException(404, "trace not found")
    return t


@router.delete("/history", tags=["history"])
def clear_history(ctx: AppContext = Depends(get_ctx)) -> dict:
    """One-click delete: traces, outbound log, saved searches, gaps, documents, pending sends, error reports."""
    ctx.db.wipe_all()
    return {"cleared": True}


@router.get("/saved-searches", tags=["history"])
def saved_searches(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    out = []
    for r in ctx.db.query("SELECT id,created_at,name,payload_enc FROM saved_search ORDER BY created_at DESC"):
        out.append({"id": r["id"], "created_at": r["created_at"], "name": r["name"], **ctx.keys.decrypt_json(r["payload_enc"])})
    return out


@router.post("/saved-searches", tags=["history"], status_code=201)
def save_search(body: SavedSearchIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    sid = uuid.uuid4().hex[:12]
    tr = ctx.db.get_trace(body.trace_id) if body.trace_id else None
    ctx.db.put_json("saved_search", "id", sid, "payload_enc", {"trace_id": body.trace_id, "note": body.note, "question": (tr or {}).get("pseudonymised_question"), "as_of": (tr or {}).get("as_of")},
                    created_at=now(), name=body.name)
    return {"id": sid}


@router.delete("/saved-searches/{sid}", tags=["history"], status_code=204)
def delete_saved(sid: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    ctx.db.execute("DELETE FROM saved_search WHERE id=?", (sid,))
    return Response(status_code=204)


@router.get("/coverage-gaps", tags=["history"])
def coverage_gaps(ctx: AppContext = Depends(get_ctx)) -> dict:
    """What the app could not answer (abstentions, failed verifications, error reports): a measure of real demand."""
    return ctx.db.gap_summary()


@router.delete("/coverage-gaps", tags=["history"])
def clear_gaps(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"deleted": ctx.db.clear_gaps()}


# ------------------------------------------------------------------------------------------------ error reports, export
@router.post("/error-reports", tags=["reports"], status_code=201)
def create_report(body: ErrorReportIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """Builds a LOCAL draft (pseudonymised question, answer, cited articles + versions). The user reads it in full, then submits."""
    return misc.create_error_report(ctx, body.trace_id, body.what_is_wrong, body.correct_source)


@router.get("/error-reports/{rid}", tags=["reports"])
def read_report(rid: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    got = ctx.db.get_json("error_report", "id", rid, "payload_enc")
    if not got:
        raise HTTPException(404)
    return {**got[0], "status": got[1]["status"]}


@router.post("/error-reports/{rid}/submit", tags=["reports"])
def submit_report(rid: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        return misc.submit_error_report(ctx, rid)
    except KeyError:
        raise HTTPException(404, "report not found")


@router.post("/export", tags=["reports"])
def export(body: ExportIn, ctx: AppContext = Depends(get_ctx)) -> Response:
    try:
        data, mime, name = misc.render_export(ctx, body.trace_id, body.format)
    except KeyError:
        raise HTTPException(404, "trace not found")
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------------------------------------------ deadline reminders
@router.post("/reminders", tags=["reminders"], status_code=201)
def create_reminder(body: ReminderIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """Local reminders for the shell to show as notifications. Shipped only once the deadline calculator matches official examples."""
    st = ctx.calcs.status.get(body.calculator_tool, {}) if ctx.calcs else {}
    if not st.get("verified"):
        raise HTTPException(409, {"code": "calculator_unverified", "reason": f"'{body.calculator_tool}' has not been verified against official worked examples, so reminders are disabled for it"})
    rid = uuid.uuid4().hex[:12]
    ctx.db.execute("INSERT INTO reminder(id,created_at,due_date,title,payload) VALUES(?,?,?,?,?)", (rid, now(), body.due_date.isoformat(), body.title, json.dumps({"tool": body.calculator_tool})))
    return {"id": rid}


@router.get("/reminders", tags=["reminders"])
def list_reminders(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return [dict(r) for r in ctx.db.query("SELECT * FROM reminder WHERE done=0 ORDER BY due_date")]
