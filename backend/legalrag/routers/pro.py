"""Professional toolkit: catalog, jobs (prepare -> preview -> run -> poll) and the rulings database."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_ctx, require_pack, require_token
from ..pro import catalog as C
from ..pro import engine as E
from ..pro.rulings import open_store, rulings_path
from ..state import AppContext

router = APIRouter(prefix="/v1/pro", dependencies=[Depends(require_token)], tags=["pro"])


@router.get("/catalog")
def catalog(ctx: AppContext = Depends(get_ctx)) -> dict:
    return C.public_catalog(open_store(ctx.settings.data_dir) is not None)


class JobIn(BaseModel):
    tool: str
    fields: dict[str, str] = Field(default_factory=dict)
    as_of: date | None = None
    lang: str = "ar"


@router.post("/jobs", status_code=201)
def prepare_job(body: JobIn, ctx: AppContext = Depends(require_pack)) -> dict:
    """Masks the inputs on the device and returns the preview of what may be sent. Nothing leaves the device yet."""
    try:
        return E.prepare(ctx, body.tool, body.fields, body.as_of, body.lang)
    except KeyError:
        raise HTTPException(404, {"code": "unknown_tool", "message": body.tool})
    except ValueError as e:
        raise HTTPException(422, {"code": "missing_field", "message": str(e)})


class RunIn(BaseModel):
    edited: dict[str, str] | None = None


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, body: RunIn | None = None, ctx: AppContext = Depends(require_pack)) -> dict:
    try:
        return E.start(ctx, job_id, (body.edited if body else None))
    except KeyError:
        raise HTTPException(404, "job not found or expired: prepare it again")


@router.get("/jobs/{job_id}")
def job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    j = E.get_job(job_id)
    if not j:
        raise HTTPException(404, "job not found or expired")
    return E.public_job(j)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, ctx: AppContext = Depends(get_ctx)) -> None:
    E.drop_job(job_id)


@router.get("/rulings/stats")
def rulings_stats(ctx: AppContext = Depends(get_ctx)) -> dict:
    st = open_store(ctx.settings.data_dir)
    if st is None:
        return {"available": False, "path": str(rulings_path(ctx.settings.data_dir))}
    return {"available": True, **st.stats()}


@router.get("/rulings/search")
def rulings_search(q: str, chamber: str | None = None, k: int = 10, ctx: AppContext = Depends(get_ctx)) -> dict:
    st = open_store(ctx.settings.data_dir)
    if st is None:
        return {"available": False, "rulings": []}
    return {"available": True, "rulings": st.search(q, k=max(1, min(k, 30)), chamber=chamber or None)}


@router.get("/rulings/{ruling_id}")
def ruling(ruling_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    st = open_store(ctx.settings.data_dir)
    r = st.get(ruling_id) if st else None
    if not r:
        raise HTTPException(404, "ruling not found")
    return r
