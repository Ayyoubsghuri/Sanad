"""AI providers chosen in the app: several can be saved (OpenAI, Anthropic, any OpenAI-compatible endpoint); one is active.
Keys go to the OS keychain and are never returned; only `has_key` is."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Response

from ..deps import get_ctx, require_token
from ..llm.providers import GenRequest
from ..schemas import ActiveIn, ProviderIn
from ..state import AppContext

router = APIRouter(prefix="/v1/llm-providers", dependencies=[Depends(require_token)], tags=["settings"])

PRESETS = [
    {"kind": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1", "models": ["gpt-4.1", "gpt-4o", "gpt-4o-mini"], "needs_key": True},
    {"kind": "anthropic", "label": "Anthropic", "base_url": "https://api.anthropic.com", "models": [], "needs_key": True},
    {"kind": "openai_compat", "label": "OpenAI-compatible (OpenRouter, Azure, local server...)", "base_url": "", "models": [], "needs_key": False},
]
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")


def _view(ctx: AppContext) -> dict:
    st = ctx.user_settings()
    provs = st.get("llm_providers") or {}
    return {
        "active": st.get("llm_active") if st.get("llm_active") in provs else None,
        "checker": st.get("llm_checker") if st.get("llm_checker") in provs else None,
        "providers": [{"id": i, **{k: c.get(k) for k in ("kind", "label", "model", "base_url")}, "has_key": ctx.keys.has_secret(ctx.provider_secret_name(i))} for i, c in provs.items()],
        "presets": PRESETS, "mode": ctx.mode, "key_storage": ctx.keys.storage,
        "environment_provider": {"provider": ctx.settings.llm_provider, "model": ctx.settings.llm_model} if ctx.settings.llm_provider != "none" else None,
    }


@router.get("")
def list_providers(ctx: AppContext = Depends(get_ctx)) -> dict:
    return _view(ctx)


@router.put("/{pid}")
def save_provider(pid: str, body: ProviderIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    if not _ID.match(pid):
        raise HTTPException(422, "id: lowercase letters, digits, - or _ (max 31)")
    if body.kind == "openai_compat" and not (body.base_url or "").startswith(("http://", "https://")):
        raise HTTPException(422, "an OpenAI-compatible provider needs a base URL (https://...)")
    if body.base_url and not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(422, "base_url must start with http:// or https://")
    st = ctx.user_settings()
    provs = dict(st.get("llm_providers") or {})
    existing = pid in provs
    if not existing and body.api_key is None and body.kind != "openai_compat":
        raise HTTPException(422, "an API key is required for a new provider")
    provs[pid] = {"kind": body.kind, "label": body.label, "model": body.model, "base_url": body.base_url if body.kind == "openai_compat" else None}
    upd: dict = {"llm_providers": provs}
    if not st.get("llm_active"):
        upd["llm_active"] = pid  # the first provider becomes the active one
    ctx.db.set_settings(upd)
    if body.api_key:
        ctx.keys.set_secret(ctx.provider_secret_name(pid), body.api_key)
    return _view(ctx)


@router.delete("/{pid}", status_code=204)
def delete_provider(pid: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    st = ctx.user_settings()
    provs = dict(st.get("llm_providers") or {})
    if pid not in provs:
        raise HTTPException(404)
    provs.pop(pid)
    upd: dict = {"llm_providers": provs}
    for k in ("llm_active", "llm_checker"):
        if st.get(k) == pid:
            upd[k] = None
    ctx.db.set_settings(upd)
    ctx.keys.delete_secret(ctx.provider_secret_name(pid))
    return Response(status_code=204)


@router.post("/active")
def set_active(body: ActiveIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    provs = ctx.user_settings().get("llm_providers") or {}
    if body.id is not None and body.id not in provs:
        raise HTTPException(404, "unknown provider")
    ctx.db.set_settings({"llm_active": body.id})
    return _view(ctx)


@router.post("/checker")
def set_checker(body: ActiveIn, ctx: AppContext = Depends(get_ctx)) -> dict:
    """A second provider that double-checks every claim against its quote (use a different model from the writer). None = local check."""
    provs = ctx.user_settings().get("llm_providers") or {}
    if body.id is not None and body.id not in provs:
        raise HTTPException(404, "unknown provider")
    ctx.db.set_settings({"llm_checker": body.id})
    return _view(ctx)


@router.post("/{pid}/test")
def test_provider(pid: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    """One tiny call that carries no user data: confirms the key, model name and endpoint work."""
    prov = ctx._provider_from_settings(pid)
    if prov is None:
        raise HTTPException(404, "provider not found or incomplete")
    if ctx.mode == "offline":
        return {"ok": False, "error": "the app is in offline mode: switch to hybrid or cloud-assisted to test a cloud provider"}
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    try:
        out = prov.generate_json(GenRequest("Reply with the JSON {\"ok\": true}.", {"ping": "test"}, schema, [], None, kind="understand"))
        return {"ok": bool(out.get("ok", True)), "model": prov.model}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{e.__class__.__name__}: {str(e)[:200]}"}
