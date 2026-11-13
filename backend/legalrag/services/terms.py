"""Arabic / French / Darija / English legal term finder: query expansion, domain detection, public term lookup."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from ..text.arabic import light_stem, normalize, tokens


@lru_cache(maxsize=1)
def glossary() -> list[dict]:
    p = Path(__file__).resolve().parent.parent / "data" / "glossary.json"
    entries = json.loads(p.read_text(encoding="utf-8"))
    for e in entries:
        e["_norm"] = {lang: [normalize(t) for t in e[lang]] for lang in ("ar", "fr", "en", "darija")}
    return entries


def _present(norm_text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", norm_text))


def match_entries(text: str) -> list[dict]:
    nt = normalize(text)
    hits = []
    for e in glossary():
        if any(_present(nt, t) for lang in e["_norm"].values() for t in lang):
            hits.append(e)
    return hits


def expand_terms(text: str) -> tuple[list[str], list[str]]:
    """Returns (extra keyword tokens from the glossary in all languages, detected domains)."""
    extra: list[str] = []
    domains: list[str] = []
    for e in match_entries(text):
        if e["domain"] not in domains:
            domains.append(e["domain"])
        for lang in ("ar", "fr", "en"):
            for t in e["_norm"][lang]:
                extra += [light_stem(x) for x in tokens(t)]
    seen, out = set(), []
    for t in extra:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out, domains


def lookup(q: str, limit: int = 10) -> list[dict]:
    """Term finder endpoint: everyday word -> legal terms in each language."""
    nq = normalize(q)
    res = []
    for e in glossary():
        score = 0
        for lang, terms in e["_norm"].items():
            for t in terms:
                if nq == t:
                    score = max(score, 3)
                elif nq in t or t in nq:
                    score = max(score, 2 if _present(nq, t) or _present(t, nq) else 1)
        if score:
            res.append((score, {"id": e["id"], "domain": e["domain"], "ar": e["ar"], "fr": e["fr"], "en": e["en"], "darija": e["darija"]}))
    res.sort(key=lambda x: -x[0])
    return [r for _, r in res[:limit]]
