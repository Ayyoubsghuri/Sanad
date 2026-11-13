"""Optional Arabic NER detector (MutazYoune/Arabic-NER-PII) as an EXTRA layer on top of the rule-based detectors.

- Runs fully on the device (transformers). The model weights are downloaded once from Hugging Face (no user text is
  sent anywhere); point `ner_model` at a local directory for air-gapped use.
- Lazy: nothing is imported or loaded until the first Arabic text is pseudonymised.
- Fails open to the rule-based detectors: if transformers/torch/the model is unavailable, `status` says why and
  pseudonymisation continues without it.
- The model has weak exact-boundary accuracy (card: exact F1 0.02, partial F1 0.53), so spans are snapped outward to
  whole words, and it can only ADD detections; it never removes any.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

from ..text.arabic import arabic_ratio
from .patterns import Span

log = logging.getLogger("legalrag.ner")

# model label (entity_group, without B-/I-) -> placeholder kind used by the vault
LABEL_TO_KIND = {
    "PII": "PERSON",
    "CONTACT": None,  # decided from the text: e-mail / phone / url
    "NETWORK": "ADDRESS",
    "IDENTIFIER": "CIN",
    "NUMERIC_ID": "CASE",
}
_WORD_CHAR = re.compile(r"[\w؀-ۿ@.+\-/]")
_CHUNK = 1500
_OVERLAP = 150


def _has_letters(s: str) -> bool:
    import re as _re
    return bool(_re.search(r"[^\W\d_]", s))


def _contact_kind(s: str) -> str:
    if "@" in s:
        return "EMAIL"
    digits = sum(c.isdigit() for c in s)
    if digits >= 7:
        return "PHONE"
    return "ADDRESS"  # URLs and similar


class NerDetector:
    def __init__(
        self,
        model: str = "MutazYoune/Arabic-NER-PII",
        enabled: bool = True,
        min_score: float = 0.5,
        kinds: tuple[str, ...] = ("PII", "CONTACT", "NETWORK", "IDENTIFIER"),
        pipeline_factory: Callable[[str], Any] | None = None,
    ):
        self.model, self.enabled, self.min_score, self.kinds = model, enabled, min_score, set(kinds)
        self._factory = pipeline_factory
        self._pipe: Any = None
        self._lock = threading.Lock()
        self.state = "idle" if enabled else "disabled"  # idle | ready | unavailable | disabled
        self.error: str | None = None

    # ---------------------------------------------------------------------------------------------
    @property
    def status(self) -> dict[str, Any]:
        return {"model": self.model, "state": self.state, "error": self.error, "kinds": sorted(self.kinds), "min_score": self.min_score}

    def _load(self) -> Any:
        if self._pipe is not None or self.state in ("unavailable", "disabled"):
            return self._pipe
        with self._lock:
            if self._pipe is not None or self.state in ("unavailable", "disabled"):
                return self._pipe
            try:
                if self._factory:
                    self._pipe = self._factory(self.model)
                else:
                    from transformers import pipeline  # optional dependency: pip install legalrag-backend[ner]

                    self._pipe = pipeline("ner", model=self.model, aggregation_strategy="simple")
                self.state = "ready"
            except Exception as e:  # missing package, no network on first run, bad path...
                self.state, self.error = "unavailable", f"{type(e).__name__}: {e}"[:300]
                log.warning("Arabic NER disabled (%s); rule-based detection continues", self.error)
        return self._pipe

    def warm_up(self) -> None:
        self._load()

    # ---------------------------------------------------------------------------------------------
    def detect(self, text: str) -> list[Span]:
        if not self.enabled or not text.strip() or arabic_ratio(text) < 0.2:
            return []
        pipe = self._load()
        if pipe is None:
            return []
        spans: list[Span] = []
        for off, chunk in self._chunks(text):
            try:
                ents = pipe(chunk)
            except Exception as e:
                self.state, self.error = "unavailable", f"{type(e).__name__}: {e}"[:300]
                log.warning("Arabic NER failed at inference: %s", self.error)
                return spans
            for ent in ents:
                label = str(ent.get("entity_group") or ent.get("entity") or "").split("-")[-1].upper()
                if label not in self.kinds or float(ent.get("score", 0)) < self.min_score:
                    continue
                s, e = self._snap(text, off + int(ent["start"]), off + int(ent["end"]))
                if e <= s:
                    continue
                kind = LABEL_TO_KIND.get(label) or _contact_kind(text[s:e])
                if kind in ("PERSON", "ORG", "ADDRESS") and not _has_letters(text[s:e]):
                    continue  # "16" in "بنت 16 سنة" came back as a person: a bare number is never a name
                spans.append(Span(kind, s, e, "ner"))
        return spans

    @staticmethod
    def _chunks(text: str):
        if len(text) <= _CHUNK:
            yield 0, text
            return
        start = 0
        while start < len(text):
            end = min(len(text), start + _CHUNK)
            if end < len(text):
                sp = text.rfind(" ", start + _CHUNK // 2, end)
                end = sp if sp > 0 else end
            yield start, text[start:end]
            if end >= len(text):
                break
            start = max(end - _OVERLAP, start + 1)

    @staticmethod
    def _snap(text: str, s: int, e: int) -> tuple[int, int]:
        """Boundaries from the model are imprecise: grow to whole words so no half-name is left behind."""
        s, e = max(0, s), min(len(text), e)
        while s > 0 and _WORD_CHAR.match(text[s - 1]):
            s -= 1
        while e < len(text) and _WORD_CHAR.match(text[e]):
            e += 1
        while e > s and text[e - 1] in ".-/+":
            e -= 1
        return s, e
