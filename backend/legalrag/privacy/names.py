"""Name detection: Moroccan name dictionary (Arabic / French / Latin spellings), titles, user-marked terms.

Recall on names is never perfect (Arabic and Darija especially), so the detector also reports unknown
capitalised Latin tokens and a per-text confidence score; callers fail closed on low confidence.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..text.arabic import normalize
from ..text.dates import MONTHS
from ..text.stopwords import AR as AR_STOP
from .patterns import Span

_TOKEN = re.compile(r"[^\W\d_][\w'’\-]*", re.UNICODE)


@dataclass(frozen=True)
class Tok:
    text: str
    norm: str
    start: int
    end: int


@dataclass
class NameData:
    first: set[str]
    sur: set[str]
    particles: set[str]
    titles: set[str]
    role_words: set[str]
    legal_caps: set[str]
    places: set[str]

    @property
    def names(self) -> set[str]:
        return self.first | self.sur


@lru_cache(maxsize=1)
def load_names(path: str | None = None) -> NameData:
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "data" / "names.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    n = lambda xs: {normalize(x) for x in xs}  # noqa: E731
    return NameData(
        first=n(d["first_names"]),
        sur=n(d["surnames"]),
        particles=n(d["particles"]),
        titles=n(d["titles_latin"]) | n(d["titles_ar"]),
        role_words=n(d["role_words_ar"]),
        legal_caps=n(d["legal_capitalised"]) | set(MONTHS),
        places=n(d["places"]),
    )


def tokenize(text: str) -> list[Tok]:
    return [Tok(m.group(0), normalize(m.group(0)).strip("'-"), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _is_latin_cap(t: Tok) -> bool:
    return t.text[:1].isupper() and t.text[:1].isascii() or (t.text[:1].isupper() and t.text[:1].isalpha())


def _arabic(t: Tok) -> bool:
    return any("؀" <= c <= "ۿ" for c in t.text)


def _adjacent(text: str, a: Tok, b: Tok) -> bool:
    gap = text[a.end:b.start]
    return gap in (" ", "  ", " ") or (gap.strip() == "" and "\n" not in gap)


def detect_names(text: str, nd: NameData) -> tuple[list[Span], list[tuple[str, int]]]:
    """Returns (PERSON spans, unknown capitalised Latin tokens as (text, start))."""
    toks = tokenize(text)
    spans: list[Span] = []
    in_span = [False] * len(toks)

    def take(i: int, j: int, origin: str) -> None:
        if i > j:
            return
        spans.append(Span("PERSON", toks[i].start, toks[j].end, origin))
        for k in range(i, j + 1):
            in_span[k] = True

    def can_extend(t: Tok) -> bool:
        if t.norm in nd.particles or t.norm in nd.names:
            return True
        if _arabic(t):
            return t.norm.startswith("ال") and t.norm not in nd.role_words and t.norm not in AR_STOP and len(t.norm) > 3
        return _is_latin_cap(t) and t.norm not in nd.legal_caps and t.norm not in nd.places and len(t.norm) > 2

    i = 0
    while i < len(toks):
        t = toks[i]
        # --- title-triggered: "M. Benali", "السيد أحمد ..." -------------------------------------
        if t.norm in nd.titles and (_arabic(t) or t.text[:1].isupper()):
            j = i
            k = i + 1
            while k < len(toks) and k - i <= 4 and _adjacent(text, toks[k - 1], toks[k]) is not False:
                nt = toks[k]
                ok = nt.norm in nd.particles or nt.norm in nd.names or (
                    (_is_latin_cap(nt) and nt.norm not in nd.legal_caps and nt.norm not in nd.places and nt.norm not in nd.titles)
                    or (_arabic(nt) and nt.norm not in AR_STOP and nt.norm not in nd.role_words and nt.norm not in nd.titles and nt.norm not in nd.places)
                )
                gap = text[toks[k - 1].end:nt.start]
                if not ok or gap.strip(" . ") != "":
                    break
                j = k
                k += 1
            if j > i:
                take(i + 1, j, "title")
                i = j + 1
                continue
        # --- dictionary-triggered -------------------------------------------------------------------
        # "على" (alef maqsura) is the preposition "on"; as a name it is written "علي".  Normalisation makes both the same word, so look at the raw spelling.
        is_hit = t.norm in nd.names and (_arabic(t) or _is_latin_cap(t)) and t.text != "على"
        if is_hit and not in_span[i]:
            j = i
            while j + 1 < len(toks) and j - i < 4 and _adjacent(text, toks[j], toks[j + 1]) and can_extend(toks[j + 1]):
                # a particle must be followed by a name token to be absorbed
                if toks[j + 1].norm in nd.particles and not (j + 2 < len(toks) and _adjacent(text, toks[j + 1], toks[j + 2]) and can_extend(toks[j + 2])):
                    break
                j += 1
            take(i, j, "dictionary")
            i = j + 1
            continue
        i += 1

    # --- unknown capitalised Latin tokens (warning only) ------------------------------------------------------
    unknown: list[tuple[str, int]] = []
    for idx, t in enumerate(toks):
        if in_span[idx] or _arabic(t) or not _is_latin_cap(t) or len(t.norm) < 3:
            continue
        if t.norm in nd.legal_caps or t.norm in nd.places or t.norm in nd.titles or t.text.isupper():
            continue
        before = text[:t.start].rstrip("  ")
        if not before or before[-1] in ".!?:\n؟" or text[max(0, t.start - 1):t.start] == "\n":
            continue  # sentence start: capitalised for grammar, not a name signal
        unknown.append((t.text, t.start))
    return spans, unknown


def find_terms(text: str, terms: list[tuple[str, str]], origin: str) -> list[Span]:
    """Occurrences of user-marked / case-vault terms (case- and diacritic-insensitive on Latin letters)."""
    out: list[Span] = []
    low = text.lower()
    for term, kind in terms:
        t = term.strip()
        if len(t) < 2:
            continue
        for m in re.finditer(re.escape(t.lower()), low):
            s, e = m.start(), m.end()
            # whole-word boundaries
            if (s > 0 and text[s - 1].isalnum()) or (e < len(text) and text[e].isalnum()):
                continue
            out.append(Span(kind, s, e, origin))
    return out


def find_places(text: str, nd: NameData) -> list[Span]:
    spans = []
    for t in tokenize(text):
        if t.norm in nd.places:
            spans.append(Span("ADDRESS", t.start, t.end, "place"))
    return spans
