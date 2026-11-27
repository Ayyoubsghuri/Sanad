"""The public API for other websites (public mode): POST /v1/public/ask with an X-Api-Key header.

One call = one question, answered and forgotten: the masked question goes through the same checks as in the app, and the
reply holds the verified statements, the articles they rest on, similar rulings and the practical steps. Nothing is kept.
A question whose masking confidence is low is not sent: the reply says so (status "review_required")."""
from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import get_ctx, require_pack
from ..pipeline.orchestrator import QueryPipeline
from ..public import Limiter, api_keys
from ..schemas import PrepareRequest, RunRequest
from ..state import AppContext

router = APIRouter(prefix="/v1/public", tags=["public api"])
_LIMITS = Limiter()


class AskIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    as_of: date | None = Field(None, description="the date whose law applies (default: today)")


def _site(request: Request, x_api_key: str | None) -> str:
    ctx: AppContext = request.app.state.ctx
    keys = api_keys(ctx.settings.public_api_keys)
    for k, site in keys.items():
        if x_api_key and hmac.compare_digest(x_api_key, k):
            return site
    raise HTTPException(401, "missing or unknown X-Api-Key")


@router.get("/info")
def info(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"name": "Sanad", "public": True, "per_key_per_day": ctx.settings.public_api_per_day,
            "law_pack": ctx.pack.version if ctx.pack else None, "notice": "Information on Moroccan law, not legal advice."}


@router.post("/ask")
def ask(body: AskIn, request: Request, x_api_key: str | None = Header(None), ctx: AppContext = Depends(require_pack)) -> dict:
    site = _site(request, x_api_key)
    ok, wait = _LIMITS.hit(f"key:{site}", None, ctx.settings.public_api_per_day)
    if not ok:
        raise HTTPException(429, {"code": "limit", "retry_after_s": wait}, headers={"Retry-After": str(wait)})
    pipe = QueryPipeline(ctx)
    try:
        prep = pipe.prepare(PrepareRequest(question=body.question, as_of=body.as_of))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if prep.get("requires_review"):
        ctx.db.delete_case(prep["case_id"])
        return {"status": "review_required", "message": "the question holds personal details that could not be masked with confidence: remove names and identifiers and ask again"}
    a = pipe.run(prep["query_id"], RunRequest(review_confirmed=True))
    srcs = {s["id"]: s for s in a.get("sources", []) + a.get("related", [])}
    cited = {sid for c in a.get("claims", []) for sid in c.get("sources", [])}
    return {
        "status": a.get("status"), "language": a.get("language"), "law_as_of": a.get("as_of"),
        "answer": [{"text": c["text"], "type": c.get("type"), "sources": c.get("sources", [])} for c in a.get("claims", [])],
        "sources": [{"id": sid, "law": s.get("law"), "article": s.get("article"), "text": s.get("text"), "bulletin": s.get("bo"),
                     "in_force": s.get("in_force_on_as_of"), "url": (s.get("source") or {}).get("url") if isinstance(s.get("source"), dict) else None}
                    for sid, s in srcs.items() if sid in cited],
        "rulings": (a.get("rulings") or {}).get("items", []),
        "next_steps": a.get("next_steps"),
        "clarifying_question": a.get("clarifying_question"),
        "notices": a.get("notices", []),
    }
