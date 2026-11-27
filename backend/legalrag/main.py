"""FastAPI application factory.  Run:  legalrag   (or: uvicorn legalrag.main:app --factory)"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .config import Settings
from .privacy.gateway import CloudUnavailable, ModeForbids, OutboundBlocked
from .routers import bo, law, providers, query, system, tools, pro, compute, public_api
from .state import AppContext, build_context

log = logging.getLogger("legalrag")


def _public_guard(app: FastAPI, settings: Settings) -> None:
    """Public mode: only the visitor's routes, questions limited per visitor, security headers. Any website may call the
    public API (it needs a key); no cookies are used, so allowing every origin exposes nothing."""
    from . import public as P

    limiter = P.Limiter()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        method, path = request.method, request.url.path
        if method != "OPTIONS":
            if not P.allowed(method, path):
                return JSONResponse(status_code=403, content={"code": "public_mode", "message": "not available on the public server"})
            if P.counted(method, path):
                ip = P.client_ip(request.headers, request.client.host if request.client else None)
                ok, wait = limiter.hit(ip, settings.public_per_hour, settings.public_per_day)
                if not ok:
                    return JSONResponse(status_code=429, headers={"Retry-After": str(wait)},
                                        content={"code": "limit", "retry_after_s": wait,
                                                 "message": f"question limit reached ({settings.public_per_hour} per hour, {settings.public_per_day} per day)"})
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Cache-Control", "no-store") if path.startswith("/v1/") else None
        return resp

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])


def create_app(settings: Settings | None = None, ctx: AppContext | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = ctx or build_context(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = ctx
        log.info("law pack: %s", ctx.pack.version if ctx.pack else ctx.pack_error)
        yield
        ctx.close()

    app = FastAPI(
        title="Moroccan Legal RAG: local backend",
        version="0.1.0",
        description="Date-aware retrieval of Moroccan law, verified citations, on-device pseudonymisation. Information only, not legal advice.",
        lifespan=lifespan,
    )
    app.state.ctx = ctx  # also available before lifespan (tests using TestClient without a context manager)
    if settings.public_mode:
        _public_guard(app, settings)
    else:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)  # DNS-rebinding guard
        # Any port on loopback is allowed (dev servers on 3000/5173/1420...). Still protected by the bearer token and the host check.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(system.public)
    app.include_router(system.router)
    app.include_router(query.router)
    app.include_router(law.router)
    app.include_router(tools.router)
    app.include_router(bo.router)
    app.include_router(providers.router)
    app.include_router(pro.router)
    app.include_router(compute.router)
    app.include_router(public_api.router)

    @app.exception_handler(OutboundBlocked)
    async def _blocked(_: Request, e: OutboundBlocked):
        return JSONResponse(status_code=409, content={"code": "outbound_blocked", "kinds": e.kinds, "message": str(e)})

    @app.exception_handler(ModeForbids)
    async def _mode(_: Request, e: ModeForbids):
        return JSONResponse(status_code=409, content={"code": "mode_forbids", "mode": e.mode, "kind": e.kind})

    @app.exception_handler(CloudUnavailable)
    async def _cloud(_: Request, e: CloudUnavailable):
        return JSONResponse(status_code=502, content={"code": "cloud_unavailable", "message": str(e)})

    if settings.frontend_dir and (settings.frontend_dir / "index.html").exists():  # mounted last: the API routes above win
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")
    return app


def run() -> None:
    s = Settings()
    ctx = build_context(s)
    if s.public_mode:
        print(f"PUBLIC MODE: nothing about visitors is stored; {s.public_per_hour}/hour and {s.public_per_day}/day per visitor")
    else:
        print(f"API token (give it to the desktop shell): {ctx.api_token}")
    uvicorn.run(create_app(s, ctx), host=s.host, port=s.port, log_level="info")


if __name__ == "__main__":
    run()
