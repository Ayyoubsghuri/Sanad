"""Public mode: what a visitor of a shared server may call, and how often.

Only the routes the chat page and the law browser need are open; settings, keys, updates, documents, the toolkit and the
logs are closed (403). Questions are limited per visitor (IP address) per hour and per day, and per website key for the
public API. Counters live in memory only."""
from __future__ import annotations

import re
import threading
import time
from collections import deque

# (method, path) a visitor may call; everything else under /v1 is refused in public mode
ALLOW: list[tuple[str, re.Pattern]] = [(m, re.compile(p)) for m, p in [
    ("POST", r"^/pair$"),
    ("GET", r"^/v1/settings$"), ("PATCH", r"^/v1/settings$"),          # PATCH is answered but changes nothing
    ("GET", r"^/v1/status$"), ("GET", r"^/v1/pack$"), ("GET", r"^/v1/pack/coverage$"),
    ("POST", r"^/v1/queries$"), ("POST", r"^/v1/queries/[\w-]+/run$"), ("GET", r"^/v1/queries/[\w-]+/progress$"),
    ("POST", r"^/v1/queries/[\w-]+/cancel$"), ("POST", r"^/v1/pseudonymise/preview$"),
    ("GET", r"^/v1/(instruments|provisions|decisions|lookup|navigator|terms|pending-bills|concordance|calculators|deadline-rules|rates)(/.*)?$"),
    ("POST", r"^/v1/(search|provisions/compare|wizard/which-rules-apply|calculators/run)$"),
    ("GET", r"^/v1/tools/(concordance|concordance/table|history|laws/[^/]+/family|guides)$"),
    ("POST", r"^/v1/tools/(calculator-basis|guides)$"),
    ("POST", r"^/v1/public/ask$"), ("GET", r"^/v1/public/info$"),
]]
# the calls that cost a model call: counted against the visitor's limits
COUNTED: list[tuple[str, re.Pattern]] = [("POST", re.compile(r"^/v1/queries$")), ("POST", re.compile(r"^/v1/tools/guides$"))]


def allowed(method: str, path: str) -> bool:
    if path == "/health" or not (path.startswith("/v1/") or path in ("/pair", "/docs", "/openapi.json", "/redoc")):
        return True   # the page itself and its files
    return any(m == method and rx.match(path) for m, rx in ALLOW)


def counted(method: str, path: str) -> bool:
    return any(m == method and rx.match(path) for m, rx in COUNTED)


def client_ip(headers, peer: str | None) -> str:
    """The visitor's address. Behind the host's proxy (Hugging Face) it is the LAST address of X-Forwarded-For, the one the
    proxy itself added: the first ones can be written by the visitor."""
    xff = headers.get("x-forwarded-for")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return peer or "unknown"


class Limiter:
    """In-memory sliding windows: at most `per_hour` and `per_day` events per key."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, per_hour: int | None, per_day: int) -> tuple[bool, int]:
        """-> (allowed, seconds to wait). Counts the event only when it is allowed."""
        now = time.time()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and q[0] < now - 86400:
                q.popleft()
            if len(q) >= per_day:
                return False, int(q[0] + 86400 - now) + 1
            if per_hour is not None:
                recent = [t for t in q if t >= now - 3600]
                if len(recent) >= per_hour:
                    return False, int(recent[0] + 3600 - now) + 1
            q.append(now)
            if len(self._hits) > 50000:   # forget the oldest visitors rather than grow without end
                for k in list(self._hits)[:10000]:
                    del self._hits[k]
            return True, 0


def api_keys(raw: str) -> dict[str, str]:
    """"site:key,site2:key2" -> {key: site}."""
    out = {}
    for part in (raw or "").split(","):
        if ":" in part:
            site, key = part.split(":", 1)
            if site.strip() and len(key.strip()) >= 16:
                out[key.strip()] = site.strip()
    return out
