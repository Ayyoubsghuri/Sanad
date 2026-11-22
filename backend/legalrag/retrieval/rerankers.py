"""Rerankers return relevance scores in 0..1 for (query, passage) pairs.

* LexicalReranker  - always available, local, no model: idf-weighted query-term coverage + bigram phrase hits.
                     It is the keyword-only fallback and what the coverage / abstention thresholds are calibrated on by default.
* CrossEncoderReranker - bge-reranker-v2-m3 (or similar) through sentence-transformers (optional dependency).
* CloudReranker    - Jina / TEI / Cohere-style /rerank endpoint through the Gateway (weak laptops).
"""
from __future__ import annotations

import math
from typing import Callable, Protocol

from ..privacy.gateway import Gateway
from ..text import stopwords
from ..text.arabic import light_stem, tokens


class Reranker(Protocol):
    name: str
    location: str

    def score(self, query: str, passages: list[str], case_id: str | None = None) -> list[float]: ...


_AR_SUFFIXES = ("ها", "هم", "هن", "كم", "نا")


def _rstem(t: str) -> str:
    """Reranker-only stem (the stored keyword index is untouched): strip "و" / "ف" before a word and a pronoun after it:
    "واستبدالها" -> "استبدال", "والي" -> "الي" (a stopword)."""
    if t and "\u0600" <= t[0] <= "\u06ff":
        if len(t) >= 4 and t[0] in "وف" and t[1:] in stopwords.ALL:
            return t[1:]
        for s in _AR_SUFFIXES:
            if t.endswith(s) and len(t) - len(s) >= 4:
                return t[: -len(s)]
    return t


def _terms(text: str) -> list[str]:
    out = []
    for t in tokens(text):
        t = _rstem(light_stem(t))
        if t in stopwords.ALL or len(t) <= 1:
            continue
        out.append(t)
    return out


class LexicalReranker:
    name = "lexical"
    location = "local"

    def score(self, query: str, passages: list[str], case_id: str | None = None) -> list[float]:
        q = _terms(query)
        if not q or not passages:
            return [0.0] * len(passages)
        docs = [_terms(p) for p in passages]
        n = len(docs)
        df = {t: sum(1 for d in docs if t in set(d)) for t in set(q)}
        idf = {t: math.log(1 + (n + 1) / (1 + df[t])) for t in df}
        total = sum(idf[t] for t in q) or 1.0
        qbigrams = set(zip(q, q[1:]))
        out = []
        for d in docs:
            ds = set(d)
            cov = sum(idf[t] for t in q if t in ds) / total
            bg = set(zip(d, d[1:]))
            bi = (len(qbigrams & bg) / len(qbigrams)) if qbigrams else 0.0
            out.append(round(min(1.0, 0.8 * cov + 0.2 * bi), 4))
        if len(set(q)) == 1:  # one word matching a passage proves nothing ("hi" is in "HI-TECH SEEDS"): keep it under the coverage threshold
            out = [round(x * 0.3, 4) for x in out]
        return out


class CrossEncoderReranker:
    """A local cross-encoder through sentence-transformers (default: BAAI/bge-reranker-v2-m3, multilingual).  It reads the question and
    one passage together and returns a 0..1 relevance score.  The scores are NOT calibrated: the abstention threshold (coverage_min_top_score)
    must be tuned on real questions (python -m legalrag.diagnose)."""

    location = "local"

    def __init__(self, model: str, max_length: int = 1024, trust_remote_code: bool = True, batch_size: int = 8):
        from sentence_transformers import CrossEncoder  # optional dependency

        self.name = model.replace("\\", "/").rstrip("/").split("/")[-1]  # a folder or a Hugging Face id: the short name
        self.batch_size = batch_size
        from ..device import pick_device

        self.device = pick_device()
        self._m = CrossEncoder(model, max_length=max_length, trust_remote_code=trust_remote_code, device=self.device)
        print(f"[reranker] {self.name} on {self.device}", flush=True)

    def score(self, query: str, passages: list[str], case_id: str | None = None) -> list[float]:
        import numpy as np

        raw = np.asarray(self._m.predict([(query, p) for p in passages], batch_size=self.batch_size, show_progress_bar=False), dtype=float).reshape(-1)
        # sentence-transformers already applies a sigmoid for a one-label model; apply it only when the values are still raw logits
        if raw.size and (raw.min() < 0.0 or raw.max() > 1.0):
            raw = 1.0 / (1.0 + np.exp(-raw))
        return [float(x) for x in raw]


class BlendedReranker:
    """The small reranker (Cloudflare option): a light cross-encoder blended with the lexical score. The abstention threshold
    (coverage_min_top_score) was set on lexical-like scores; the blend keeps the scores on that scale while the model reorders
    the passages by meaning."""
    location = "local"

    def __init__(self, model: "CrossEncoderReranker", weight: float = 0.6):
        self.model, self.weight, self.lex = model, weight, LexicalReranker()
        self.name = f"{model.name}+lexical"

    def score(self, query: str, passages: list[str], case_id: str | None = None) -> list[float]:
        m = self.model.score(query, passages, case_id)
        lx = self.lex.score(query, passages, case_id)
        return [round(self.weight * a + (1 - self.weight) * b, 4) for a, b in zip(m, lx)]


class CloudReranker:
    location = "cloud"

    def __init__(self, model: str, url: str, gateway: Gateway, key_getter: Callable[[], str | None]):
        self.name, self.model, self.url, self.gateway, self.key_getter = model, model, url, gateway, key_getter

    def score(self, query: str, passages: list[str], case_id: str | None = None) -> list[float]:
        key = self.key_getter()
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
        data = self.gateway.post_json(
            kind="rerank", provider="cloud-reranker", model=self.model, url=self.url, headers=headers,
            body={"model": self.model, "query": query, "documents": passages, "top_n": len(passages)},
            user_fields=[query], case_id=case_id,
        )
        scores = [0.0] * len(passages)
        for r in data.get("results", []):
            scores[r["index"]] = float(r.get("relevance_score", r.get("score", 0.0)))
        return scores
