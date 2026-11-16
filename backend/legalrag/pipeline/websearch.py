"""Web research (the compass button in the app): links from official Moroccan legal websites, shown under the answer.

Off by default and only in Hybrid mode (it is an online call). What leaves the computer is a short search query made from the
PSEUDONYMISED question: placeholders such as [PERSON_1] are removed, and if a direct identifier (ID card, phone, e-mail, RIB, file
number...) is still found, nothing is sent. Every query is written to the outbound log like the model calls.

The results are LINKS, kept apart from the answer: they are never given to the model and never cited as the law. Only pages of
official sites are kept (the government, the courts, parliament, the official bulletin); anything else the search engine returns
is dropped. The search engine is DuckDuckGo's HTML page, which needs no key."""
from __future__ import annotations

import hashlib
import html
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..privacy.patterns import DIRECT_IDENTIFIER_KINDS, detect_patterns

ENDPOINT = "https://html.duckduckgo.com/html/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sanad-web-research"}
# the official sites a result may come from (the host or any sub-domain of it)
OFFICIAL = ("gov.ma", "sgg.gov.ma", "justice.gov.ma", "adala.justice.gov.ma", "cspj.ma", "juriscassation.cspj.ma", "cour-constitutionnelle.ma",
            "chambredesrepresentants.ma", "chambredesconseillers.ma", "cndp.ma", "maroc.ma", "bkam.ma", "cese.ma", "mmsp.gov.ma",
            "emploi.gov.ma", "finances.gov.ma", "tax.gov.ma", "douane.gov.ma", "ancfcc.gov.ma", "cnss.ma", "ompic.ma", "pmp.ma")
SITES = ("sgg.gov.ma", "adala.justice.gov.ma", "cspj.ma", "chambredesrepresentants.ma", "cour-constitutionnelle.ma")
MAX_RESULTS = 5
_PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")
_RESULT = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="[^"]*result__a|\Z)', re.S)
_SNIPPET = re.compile(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div|td)>', re.S)
_TAG = re.compile(r"<[^>]+>")


def official(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return urlparse(url).scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in OFFICIAL)


def make_query(text: str) -> str | None:
    """The words to search for, from the pseudonymised question; None when an identifier is still there."""
    q = _PLACEHOLDER.sub(" ", text or "")
    q = re.sub(r"\s+", " ", q).strip()[:200]
    if len(q) < 4:
        return None
    if any(s.kind in DIRECT_IDENTIFIER_KINDS for s in detect_patterns(q)):
        return None
    return q


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", html.unescape(_TAG.sub("", s or "")))).strip()


def _target(href: str) -> str:
    """DuckDuckGo wraps each link (//duckduckgo.com/l/?uddg=<url>): unwrap it."""
    h = html.unescape(href)
    if h.startswith("//"):
        h = "https:" + h
    u = urlparse(h)
    if u.hostname and u.hostname.endswith("duckduckgo.com"):
        got = parse_qs(u.query).get("uddg")
        if got:
            return unquote(got[0])
    return h


def parse(page: str) -> list[dict[str, str]]:
    out, seen = [], set()
    for href, title, rest in _RESULT.findall(page or ""):
        url = _target(href)
        if not official(url) or url in seen:
            continue
        seen.add(url)
        sn = _SNIPPET.search(rest)
        out.append({"title": _clean(title)[:200], "url": url, "site": (urlparse(url).hostname or "").removeprefix("www."),
                    "snippet": _clean(sn.group(1))[:400] if sn else ""})
        if len(out) >= MAX_RESULTS:
            break
    return out


def run(ctx, text: str, case_id: str | None, client: httpx.Client | None = None) -> dict[str, Any]:
    """-> {"query", "results": [...]} or {"skipped": reason}. Never raises: the answer is never lost over the web search."""
    if ctx.mode == "offline":
        return {"skipped": "offline"}
    q = make_query(text)
    if q is None:
        return {"skipped": "identifier"}
    full = f"{q} ({' OR '.join('site:' + s for s in SITES)})"
    log_id = ctx.db.log_outbound(kind="web_search", provider="duckduckgo", model=None, host=urlparse(ENDPOINT).netloc, case_id=case_id,
                                 sha256=hashlib.sha256(full.encode()).hexdigest(), bytes=len(full.encode()), status="sending", payload=full)
    t0 = time.monotonic()
    c = client or httpx.Client(timeout=15, follow_redirects=True, headers=UA)
    try:
        r = c.post(ENDPOINT, data={"q": full, "kl": "xa-ar"})
        r.raise_for_status()
        results = parse(r.text)
        if not results:   # the site: filter gave nothing: ask again without it, official pages are still the only ones kept
            r = c.post(ENDPOINT, data={"q": q + " المغرب"})
            r.raise_for_status()
            results = parse(r.text)
        ctx.db.update_outbound(log_id, status="ok", latency_ms=int((time.monotonic() - t0) * 1000))
        return {"query": q, "results": results}
    except Exception as e:  # noqa: BLE001
        ctx.db.update_outbound(log_id, status="error", error=e.__class__.__name__, latency_ms=int((time.monotonic() - t0) * 1000))
        return {"query": q, "results": [], "error": f"web search unavailable ({e.__class__.__name__})"}
    finally:
        if client is None:
            c.close()
