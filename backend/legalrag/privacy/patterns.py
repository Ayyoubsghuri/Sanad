"""Pattern detectors for direct identifiers (high recall, run on the device).

Formats flagged in the blueprint as "confirm against official examples" (RIB, ICE, IF, RC, CNSS) are
matched by length/context only; no checksum is enforced until it is verified against official samples.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MONTH_WORDS = (
    r"janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre|january|february|march|april|june|july|august|september|october|november|december|"
    r"يناير|فبراير|مارس|أبريل|ابريل|ماي|يونيو|يوليوز|يوليو|غشت|شتنبر|سبتمبر|أكتوبر|اكتوبر|نونبر|نوفمبر|دجنبر|ديسمبر"
)
_DATE = rf"(?:\d{{1,2}}\s*[/.\-]\s*\d{{1,2}}\s*[/.\-]\s*\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:er)?\s+(?:{MONTH_WORDS})\s+\d{{4}})"


@dataclass(frozen=True)
class Span:
    kind: str
    start: int
    end: int
    origin: str = "pattern"

    @property
    def length(self) -> int:
        return self.end - self.start


# priority: lower number wins an overlap
PRIORITY = {"EMAIL": 1, "RIB": 2, "ICE": 2, "CIN": 3, "PHONE": 3, "CASE": 4, "PLATE": 4, "DOB": 4, "COMPANYID": 4, "ADDRESS": 5, "ORG": 6, "PERSON": 7}
DIRECT_IDENTIFIER_KINDS = {"EMAIL", "RIB", "ICE", "CIN", "PHONE", "CASE", "PLATE", "COMPANYID", "DOB"}

_RX: list[tuple[str, re.Pattern, int]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+"), 0),
    # 24-digit RIB (separators allowed); ICE = 15 digits
    ("RIB", re.compile(r"(?<![\d])(?:\d[ .\-]?){23}\d(?![\d])"), 0),
    ("ICE", re.compile(r"(?<![\d])\d{15}(?![\d])"), 0),
    ("PHONE", re.compile(r"(?<![\d+])(?:\+212|00212|0)[ .\-]?\(?0?\)?[ .\-]?[5-8][ .\-]?\d{2}[ .\-]?\d{2}[ .\-]?\d{2}[ .\-]?\d{2}(?![\d])"), 0),
    # bare uppercase CIN (1-2 letters + 5-6 digits)
    ("CIN", re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,2}\s?\d{5,6}(?![\dA-Za-z])"), 0),
    # CIN with context keyword, any case / Arabic letters
    ("CIN", re.compile(r"(?:\bCIN\b|C\.I\.N|carte nationale|بطاقة التعريف الوطنية|رقم البطاقة)\W{0,12}([A-Za-zء-ي]{1,2}\s?\d{5,6})(?![\d])", re.I), 1),
    ("CASE", re.compile(r"(?<![\d/])\d{1,5}/\d{3,4}/\d{4}(?![\d/])"), 0),
    ("CASE", re.compile(r"(?:ملف|قرار|حكم|dossier|affaire|jugement|arr[êe]t)\s*(?:عدد|رقم|n°|no\.?|num[ée]ro)\s*:?\s*(\d{1,6}(?:/\d{1,6}){0,3})(?![\d]|[.,]\d)", re.I), 1),  # a dotted number ("القرار رقم 666.25", "المرسوم 2.24.865") is a LAW number, public, not a case number
    ("PLATE", re.compile(r"(?<![\d])\d{1,5}\s?[-–]\s?[A-Za-zء-ي]\s?[-–]\s?\d{1,2}(?![\d])"), 0),
    ("DOB", re.compile(rf"(?:\bn[ée]e?\s+le|date de naissance|born on|\bDOB\b|تاريخ الازدياد|تاريخ الميلاد|ازداد(?:ت)?\s+في|ولد(?:ت)?\s+في)\s*:?\s*({_DATE})", re.I), 1),
    ("COMPANYID", re.compile(r"(?:\bIF\b|I\.F\.?|identifiant fiscal|الرقم التعريفي الضريبي)\W{0,8}(\d{6,9})(?![\d])", re.I), 1),
    ("COMPANYID", re.compile(r"(?:\bRC\b|registre de commerce|السجل التجاري)\W{0,10}(\d{3,8})(?![\d])", re.I), 1),
    ("COMPANYID", re.compile(r"(?:\bCNSS\b|\bCNOPS\b|الضمان الاجتماعي|رقم الانخراط)\W{0,14}(\d{6,10})(?![\d])", re.I), 1),
    (
        "ADDRESS",
        re.compile(
            r"(?:\b(?:n°\s*\d+\s*,?\s*)?(?:rue|avenue|av\.|boulevard|bd\.?|r[ée]sidence|immeuble|lotissement|quartier|hay|derb|route|impasse|angle)\s+[^\n,;.]{2,60})"
            r"|(?:(?<![\w\u0600-\u06FF])(?:شارع|زنقة|زنقه|درب|حي|دوار|تجزئة|إقامة|اقامة|عمارة)\s+[^\n,;،.]{2,50})",  # whole word: "الصحي" is not "حي"
            re.I,
        ),
        0,
    ),
    (
        "ORG",
        re.compile(
            r"\b(?:Soci[ée]t[ée]|Ste|SARL|S\.A\.R\.L\.?|SAS|SNC|Association|Entreprise|[ÉE]tablissements?|Ets)\s+[A-Z][\w&'’\-]*(?:\s+[A-Z][\w&'’\-]*){0,3}"
            r"|(?:شركة|مؤسسة|جمعية)\s+(?!ال)[ء-ي\w&\-]+(?:\s+(?!ال)[ء-ي\w&\-]+){0,2}"
        ),
        0,
    ),
]


def detect_patterns(text: str) -> list[Span]:
    spans: list[Span] = []
    for kind, rx, grp in _RX:
        for m in rx.finditer(text):
            s, e = (m.start(grp), m.end(grp)) if grp else (m.start(), m.end())
            if s == e or s < 0:
                continue
            # trim trailing spaces/punctuation that regexes may swallow
            while e > s and text[e - 1] in " .,;:-":
                e -= 1
            spans.append(Span(kind, s, e))
    return spans


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Greedy: lower priority number first, then longer span; drop anything overlapping an accepted span."""
    ordered = sorted(spans, key=lambda s: (PRIORITY.get(s.kind, 9), -s.length, s.start))
    kept: list[Span] = []
    for s in ordered:
        if all(s.end <= k.start or s.start >= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)
