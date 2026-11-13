"""Arabic / French normalisation used for indexing, queries, quote checks and detection.

One function (`normalize`) is applied to BOTH sides of every comparison (index text, query,
quote-vs-chunk check) so that diacritics, alef/ya/ta-marbuta variants, tatweel, Arabic-Indic
digits and French accents never cause a false mismatch.
"""
from __future__ import annotations

import re
import unicodedata

_TATWEEL = "ـ"
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_PUNCT = str.maketrans(
    {"’": "'", "‘": "'", "“": '"', "”": '"', "«": '"', "»": '"', "،": ",", "؛": ";", "؟": "?", "–": "-", "—": "-", " ": " "}
)
_LETTER_MAP = str.maketrans(
    {"ى": "ي", "ی": "ي", "ة": "ه", "ٱ": "ا", "ک": "ك", "ھ": "ه", "ۃ": "ه"}
)
_WS = re.compile(r"\s+")
_WORD = re.compile(r"\w+", re.UNICODE)
_AR_RANGE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
# U+FD3E/FD3F are the ornate Quran brackets ﴿ ﴾ (real characters in verses), not extraction damage
_PRESENTATION_FORMS = re.compile(r"[\uFB50-\uFD3D\uFD40-\uFDFF\uFE70-\uFEFF]")

# definite-article style prefixes, longest first (applied only to keyword indexing)
_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")


def normalize(text: str | None) -> str:
    """Canonical comparison form: NFKD, drop combining marks, unify letters/digits/punctuation, lowercase."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.replace(_TATWEEL, "")
    t = t.translate(_DIGITS).translate(_PUNCT).translate(_LETTER_MAP)
    t = t.replace("œ", "oe").replace("æ", "ae").lower()
    return _WS.sub(" ", t).strip()


def compact_acronyms(norm_text: str) -> str:
    """'c.p.c' -> 'cpc', 'ق.ل.ع' -> 'قلع' (dots between letters only). Expects normalised text."""
    return re.sub(r"(?<=\w)\.(?=\w)", "", norm_text)


def has_arabic(text: str) -> bool:
    return bool(_AR_RANGE.search(text or ""))


def arabic_ratio(text: str) -> float:
    letters = [c for c in (text or "") if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _AR_RANGE.match(c)) / len(letters)


def presentation_form_count(text: str) -> int:
    """Visual-order PDF extraction often leaks Arabic presentation forms; builder flags these."""
    return len(_PRESENTATION_FORMS.findall(text or ""))


def tokens(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def light_stem(tok: str) -> str:
    """Strip Arabic definite-article prefixes; leave other scripts untouched."""
    if len(tok) > 4 and _AR_RANGE.match(tok[0]):
        for p in _AR_PREFIXES:
            if tok.startswith(p) and len(tok) - len(p) >= 3:
                return tok[len(p):]
    return tok


def keyword_text(text: str) -> str:
    """Text stored in / queried against the FTS5 index."""
    return " ".join(light_stem(t) for t in tokens(text))


_QPUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def _qflat(s: str) -> str:
    """Letters, digits and single spaces only: "،" vs ",", quotes «» vs "", a dash before a list item do not make a quote false."""
    return re.sub(r"\s+", " ", _QPUNCT.sub(" ", normalize(s))).strip()


def quote_in(quote: str, haystack: str) -> bool:
    """True if `quote` is in `haystack` word for word, after normalisation.  Punctuation and spacing are ignored; a quote cut with "…" /
    "..." must have every piece (at least 2 words each) in the passage, in that order.  Words themselves must match exactly."""
    q = normalize(quote)
    h = normalize(haystack)
    if q and q in h:
        return True
    hay = _qflat(haystack)
    pieces = [_qflat(x) for x in re.split(r"…|\.{3,}|\[\s*\.\.\.\s*\]", quote)]
    pieces = [x for x in pieces if x]
    if not pieces or any(len(x.split()) < 2 and len(pieces) > 1 for x in pieces):
        return False
    pos = 0
    for x in pieces:
        i = hay.find(x, pos)
        if i < 0:
            return False
        pos = i + len(x)
    return True


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> list[str]:
    """All numeric tokens (normalised digits, thousands separators stripped) for the stray-number check."""
    out = []
    for m in _NUM.findall(normalize(text)):
        out.append(canonical_number(m))
    return out


def canonical_number(s: str) -> str:
    s = s.strip().replace(" ", "")
    # "1,000" / "1.000" thousands vs "17,92" / "17.92" decimals: decide by trailing group length
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        return s.replace(",", "").replace(".", "")
    s = s.replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
