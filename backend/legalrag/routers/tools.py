"""Tools for the app's tool windows: old->new article finder, article history, contract checker, calculators' legal basis, guides."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..calc.basis import calc_articles
from ..deps import require_pack, require_token
from ..services import misc
from ..services import review as rv
from ..services import tools as T
from ..state import AppContext

router = APIRouter(prefix="/v1/tools", dependencies=[Depends(require_token)], tags=["tools"])


def _wrap(fn, *a, **k):
    try:
        return fn(*a, **k)
    except T.ToolError as e:
        raise HTTPException(e.status, e.detail())


@router.get("/concordance")
def concordance(ref: str | None = None, instrument: str | None = None, article: str | None = None, target: str | None = None, as_of: date | None = None,
                k: int = 5, lang: str = "ar", ctx: AppContext = Depends(require_pack)) -> dict:
    """Old -> new article finder. `ref` = free text ("الفصل 440 من قانون المسطرة المدنية") or `instrument` + `article`. `target` defaults to the law that replaced it."""
    return _wrap(T.find_new_article, ctx.pack, ref, instrument, article, target, as_of, k, lang)


@router.get("/concordance/table")
def concordance_table(instrument: str, target: str | None = None, as_of: date | None = None, lang: str = "ar", ctx: AppContext = Depends(require_pack)) -> dict:
    """Whole-law map: every article of the old text with its best match in the new one."""
    return _wrap(T.concordance_table, ctx.pack, instrument, target, as_of, lang)


@router.get("/history")
def history(ref: str | None = None, instrument: str | None = None, article: str | None = None, as_of: date | None = None, lang: str = "ar",
            ctx: AppContext = Depends(require_pack)) -> dict:
    """Every text an article had across the law's editions, with word diffs and the version in force on `as_of`."""
    return _wrap(T.article_history, ctx.pack, ref, instrument, article, as_of, lang)


@router.get("/laws/{iid}/family")
def law_family(iid: str, ctx: AppContext = Depends(require_pack)) -> dict:
    """The editions of one law the pack holds (oldest first) and the law that replaced it."""
    if iid not in ctx.pack.instrument_ids():
        raise HTTPException(404, {"code": "unknown_law", "message": iid})
    fam = T.family(ctx.pack, iid)
    return {"base": T.base_id(ctx.pack, iid), "editions": [{"instrument_id": i, "title_ar": (ctx.pack.instrument(i) or {}).get("title_ar")} for i in fam],
            "replaced_by": T.successor_of(ctx.pack, fam[-1] if fam else iid)}


class ContractIn(BaseModel):
    doc_id: str | None = Field(None, description="an uploaded document (POST /v1/documents), reviewed if it asked for review")
    text: str | None = Field(None, max_length=60000, description="or pasted text; it is masked on the device before any search or model call")
    as_of: date | None = None
    lang: str = "ar"


@router.post("/contract-check")
def contract_check(body: ContractIn, ctx: AppContext = Depends(require_pack)) -> dict:
    try:
        return rv.check_document(ctx, body.doc_id, body.text, body.as_of, body.lang)
    except KeyError:
        raise HTTPException(404, "document not found")
    except PermissionError as e:
        raise HTTPException(409, {"code": "review_required", "message": str(e)})
    except ValueError as e:
        raise HTTPException(422, str(e))


class CalcBasisIn(BaseModel):
    tool: str
    on: date | None = None


@router.post("/calculator-basis")
def calculator_basis(body: CalcBasisIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """The articles behind a calculator (before any number is entered), quoted from the pack on the date."""
    on = body.on or ctx.today_fn()
    return {"tool": body.tool, "on": on.isoformat(), "articles": calc_articles(ctx.pack, body.tool, on)}


@router.get("/guides")
def guide_list() -> list[dict]:
    return [{"id": k, "label": v["label"]} for k, v in misc.SITUATIONS.items()]


class GuideIn(BaseModel):
    situation: str | None = Field(None, description="an id from GET /guides")
    topic: str | None = Field(None, max_length=300, description="or any situation in words")
    as_of: date | None = None
    lang: str = "ar"


@router.post("/guides")
def guide(body: GuideIn, ctx: AppContext = Depends(require_pack)) -> dict[str, Any]:
    """Articles + a short checklist generated from the pack for a situation (cached per pack version)."""
    if body.situation:
        s = misc.SITUATIONS.get(body.situation)
        if not s:
            raise HTTPException(404, "unknown situation")
        return rv.build_guide(ctx, body.situation, s["queries"], body.as_of, body.lang, s["label"].get(body.lang) or s["label"]["en"])
    if not body.topic:
        raise HTTPException(422, "give `situation` or `topic`")
    return rv.build_guide(ctx, body.topic, [body.topic], body.as_of, body.lang)
