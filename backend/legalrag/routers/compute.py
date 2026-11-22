"""Search by meaning: local models or Cloudflare Workers AI (the choice made in the setup, changeable in the app).

GET  /v1/compute        what is in use, the computer's memory, whether the local models are installed, the Cloudflare account
POST /v1/compute        {"source": "local"|"cloudflare", "account": "...", "token": "..."} (the token goes to the keychain)
POST /v1/compute/test   one call to Cloudflare with a test sentence"""
from __future__ import annotations

import importlib.util
import os
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_ctx, require_token
from ..state import AppContext

router = APIRouter(prefix="/v1/compute", dependencies=[Depends(require_token)], tags=["settings"])
MIN_RAM_GB = 15   # a "16 GB" computer reports a little less than 16 GB


def ram_gb() -> float | None:
    """The computer's installed memory in GB (None when unknown)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 1024**3, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except Exception:  # noqa: BLE001
        return None


def local_models_installed(ctx: AppContext) -> bool:
    if importlib.util.find_spec("sentence_transformers") is None:
        return False
    eid = ctx.pack_embedder_id()
    model = (ctx.pack.embedders().get(eid) or {}).get("model") if (ctx.pack and eid) else None
    return bool(model and (ctx.settings.resolved_embed_model_dir(model) / "config.json").exists())


def view(ctx: AppContext) -> dict:
    ram = ram_gb()
    return {
        "source": ctx.embeddings_source(), "ram_gb": ram, "min_ram_gb": 16, "low_ram": ram is not None and ram < MIN_RAM_GB,
        "local_models_installed": local_models_installed(ctx), "cloudflare_account": ctx.user_settings().get("cloudflare_account") or "",
        "cloudflare_token_saved": ctx.keys.has_secret("cloudflare_token"), "cloudflare_ready": ctx.cloudflare_ready(),
        "offline": ctx.mode == "offline", "pack_has_bge_m3": bool(ctx.pack_embedder_id()),
    }


class ComputeIn(BaseModel):
    source: str | None = Field(None, pattern="^(local|cloudflare)$")
    account: str | None = Field(None, max_length=64)
    token: str | None = Field(None, min_length=20, max_length=256)


@router.get("")
def get_compute(ctx: AppContext = Depends(get_ctx)) -> dict:
    return view(ctx)


@router.post("")
def set_compute(body: ComputeIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    if body.account is not None:
        acct = body.account.strip()
        if acct and not (len(acct) == 32 and all(c in "0123456789abcdef" for c in acct.lower())):
            raise HTTPException(422, "a Cloudflare account ID is 32 letters and digits (Cloudflare dashboard → Workers AI → Use REST API)")
        ctx.db.set_settings({"cloudflare_account": acct.lower() or None})
    if body.token:
        ctx.keys.set_secret("cloudflare_token", body.token.strip())
    if body.source == "local" and not local_models_installed(ctx):
        raise HTTPException(409, "the local models are not installed: start 'Sanad - repair setup' and choose 'Install the models'")
    if body.source:
        ctx.db.set_settings({"embeddings_source": body.source})
    return view(ctx)


@router.post("/test")
def test_compute(ctx: AppContext = Depends(get_ctx)) -> dict:
    if ctx.mode == "offline":
        raise HTTPException(409, "Offline mode: nothing is sent; switch to Hybrid to use Cloudflare")
    if not ctx.cloudflare_ready():
        raise HTTPException(409, "add the Cloudflare account ID and API token first")
    from ..retrieval.embedders import CloudflareEmbedder

    emb = CloudflareEmbedder(ctx.pack_embedder_id() or "bge-m3", lambda: ctx.user_settings().get("cloudflare_account"), ctx._key("cloudflare_token"), ctx.gateway)
    try:
        v = emb.embed(["ما هي مدة فترة الاختبار في عقد الشغل؟"])
    except Exception as e:  # noqa: BLE001 - shown in the app
        msg = str(e)
        if "401" in msg or "403" in msg or "10000" in msg:
            msg = "Cloudflare refused the token: check that it has the 'Workers AI' permission and belongs to this account"
        return {"ok": False, "error": msg[:300]}
    return {"ok": True, "dimensions": int(v.shape[1])}
