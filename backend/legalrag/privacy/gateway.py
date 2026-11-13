"""The single choke point for everything that leaves the device.

Every cloud call (language model, claim check, cloud embedder / reranker, error report) goes through
`Gateway.post_json`, which (1) enforces the operating mode, (2) re-scans the user-derived fields for
residual identifiers and fails closed, (3) writes the exact pseudonymised payload to the outbound log,
(4) applies the cloud timeout. Public law passages are declared separately and are not scanned.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from ..store.userdb import UserDB
from ..text.arabic import normalize
from . import names as N
from .patterns import DIRECT_IDENTIFIER_KINDS, detect_patterns

# which call kinds each operating mode may make
MODE_ALLOWS = {
    "offline": set(),
    "hybrid": {"understand", "generate", "claim_check", "error_report", "rewrite", "summary", "research", "plan"},
    "cloud_assisted": {"understand", "generate", "claim_check", "error_report", "rewrite", "summary", "research", "plan", "embed", "rerank"},
}


class OutboundBlocked(Exception):
    """A payload still contained an identifier; nothing was sent."""

    def __init__(self, kinds: list[str]):
        super().__init__(f"outbound payload blocked: residual identifiers detected ({', '.join(kinds)})")
        self.kinds = kinds


class ModeForbids(Exception):
    def __init__(self, mode: str, kind: str):
        super().__init__(f"operating mode '{mode}' does not allow cloud calls of kind '{kind}'")
        self.mode, self.kind = mode, kind


class CloudUnavailable(Exception):
    pass


class OutboundGuard:
    def __init__(self, db: UserDB, nd: N.NameData | None = None):
        self.db = db
        self.nd = nd or N.load_names()

    def scan(self, texts: list[str], case_id: str | None) -> list[str]:
        """Kinds of residual personal data found in the user-derived texts (empty = clean)."""
        found: set[str] = set()
        originals: list[str] = []
        if case_id:
            originals += [o for (_k, o) in self.db.vault_all(case_id).values()]
        originals += [t for t, _k in self.db.marked_terms()]
        for text in texts:
            if not text:
                continue
            for sp in detect_patterns(text):
                if sp.kind in DIRECT_IDENTIFIER_KINDS:
                    found.add(sp.kind)
            name_spans, _ = N.detect_names(text, self.nd)
            if name_spans:
                found.add("PERSON")
            nt = normalize(text)
            for o in originals:
                no = normalize(o)
                if len(no) >= 3 and no in nt:
                    found.add("VAULT_VALUE")
        return sorted(found)


class Gateway:
    def __init__(self, db: UserDB, guard: OutboundGuard, mode_getter: Callable[[], str], timeout_s: float = 10.0, transport: httpx.BaseTransport | None = None):
        self.db, self.guard, self.mode_getter, self.timeout_s = db, guard, mode_getter, timeout_s
        self._client = httpx.Client(transport=transport, timeout=timeout_s)

    @property
    def mode(self) -> str:
        return self.mode_getter()

    def allowed(self, kind: str) -> bool:
        return kind in MODE_ALLOWS.get(self.mode, set())

    def post_json(
        self,
        *,
        kind: str,
        provider: str,
        model: str | None,
        url: str,
        headers: dict[str, str] | None,
        body: dict[str, Any],
        user_fields: list[str],
        case_id: str | None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if not self.allowed(kind):
            raise ModeForbids(self.mode, kind)
        leaked = self.guard.scan(user_fields, case_id)
        if leaked:
            self.db.log_outbound(kind=kind, provider=provider, model=model, host=urlparse(url).netloc, case_id=case_id, status="blocked", error=",".join(leaked))
            raise OutboundBlocked(leaked)
        payload = json.dumps(body, ensure_ascii=False)
        raw = payload.encode("utf-8")
        log_id = self.db.log_outbound(
            kind=kind, provider=provider, model=model, host=urlparse(url).netloc, case_id=case_id,
            sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), status="sending", payload=payload,
        )
        t0 = time.monotonic()
        try:
            r = self._client.post(url, headers=headers or {}, content=raw, timeout=timeout or self.timeout_s)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            self.db.update_outbound(log_id, status="error", error=e.__class__.__name__, latency_ms=int((time.monotonic() - t0) * 1000))
            resp = getattr(e, "response", None)
            why = f" HTTP {resp.status_code}: {resp.text[:200]}" if resp is not None else ""
            raise CloudUnavailable(f"{kind} call to {provider} failed: {e.__class__.__name__}{why}") from e
        self.db.update_outbound(log_id, status="ok", latency_ms=int((time.monotonic() - t0) * 1000))
        return data
