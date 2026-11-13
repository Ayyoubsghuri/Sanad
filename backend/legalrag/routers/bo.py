"""Bulletin Officiel auto-update: one button in the app.  POST starts the job, GET returns live progress."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..bo_update.runner import BoUpdater
from ..deps import get_ctx, require_token
from ..state import AppContext

router = APIRouter(prefix="/v1/bo", dependencies=[Depends(require_token)], tags=["bulletin-officiel"])


class UpdateIn(BaseModel):
    dry_run: bool = False  # only look for new issues, download nothing


def updater(ctx: AppContext = Depends(get_ctx)) -> BoUpdater:
    u = getattr(ctx, "bo_updater", None)
    if u is None:
        u = ctx.bo_updater = BoUpdater(ctx)  # type: ignore[attr-defined]
    return u


@router.get("/status")
def status(u: BoUpdater = Depends(updater)) -> dict:
    """What an update would need (problems), the newest issue we have, and the current/last job."""
    return u.status()


@router.post("/update", status_code=202)
def start_update(body: UpdateIn | None = None, u: BoUpdater = Depends(updater)) -> dict:
    bad = u.problems()
    if bad:
        raise HTTPException(409, {"code": "update_not_possible", "reason": bad[0], "problems": bad})
    try:
        return u.start(bool(body and body.dry_run)).to_dict()
    except RuntimeError as e:
        raise HTTPException(409, {"code": "update_running", "reason": str(e)})


@router.get("/update")
def progress(u: BoUpdater = Depends(updater)) -> dict:
    if not u.job:
        raise HTTPException(404, "no update has run yet")
    return u.job.to_dict()


@router.post("/update/cancel")
def cancel(u: BoUpdater = Depends(updater)) -> dict:
    return {"cancelling": u.cancel()}
