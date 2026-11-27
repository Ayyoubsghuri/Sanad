from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request

from .pipeline.orchestrator import QueryPipeline
from .state import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def require_token(request: Request, authorization: str | None = Header(None), x_legalrag_token: str | None = Header(None)) -> None:
    """Local API token (generated on first run, readable only by the desktop shell). Stops other local web pages / processes from using the API."""
    ctx: AppContext = request.app.state.ctx
    if ctx.settings.public_mode:   # a shared server: no token; the public-mode middleware lets only the visitor's routes through
        return
    supplied = x_legalrag_token or (authorization[7:] if authorization and authorization.lower().startswith("bearer ") else "")
    if not supplied or not hmac.compare_digest(supplied, ctx.api_token):
        raise HTTPException(401, "missing or invalid API token")


def require_pack(ctx: AppContext = Depends(get_ctx)) -> AppContext:
    if not ctx.pack_usable():
        raise HTTPException(503, {"code": "pack_unavailable", "reason": ctx.pack_error or "no law pack loaded"})
    return ctx


def get_pipeline(ctx: AppContext = Depends(get_ctx)) -> QueryPipeline:
    return QueryPipeline(ctx)
