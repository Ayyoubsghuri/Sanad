"""Date extraction (Arabic / French / English) and the device-clock resolution of relative phrases."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .arabic import normalize

MONTHS: dict[str, int] = {}
for _m, _names in {
    1: ["janvier", "january", "jan", "يناير", "كانون الثاني"],
    2: ["fevrier", "february", "feb", "فبراير", "شباط"],
    3: ["mars", "march", "مارس", "اذار"],
    4: ["avril", "april", "ابريل", "نيسان"],
    5: ["mai", "may", "ماي", "ايار"],
    6: ["juin", "june", "يونيو", "حزيران"],
    7: ["juillet", "july", "يوليوز", "يوليو", "تموز"],
    8: ["aout", "august", "غشت", "اغسطس", "اب"],
    9: ["septembre", "september", "شتنبر", "سبتمبر", "ايلول"],
    10: ["octobre", "october", "اكتوبر", "تشرين الاول"],
    11: ["novembre", "november", "نونبر", "نوفمبر", "تشرين الثاني"],
    12: ["decembre", "december", "دجنبر", "ديسمبر", "كانون الاول"],
}.items():
    for _n in _names:
        MONTHS[normalize(_n)] = _m

_MONTH_ALT = "|".join(sorted((re.escape(k) for k in MONTHS), key=len, reverse=True))

_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DMY = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?!\d)")
_D_MON_Y = re.compile(rf"(?<!\d)(\d{{1,2}})(?:er|st|nd|rd|th)?\s+(?:de\s+|d'\s*)?({_MONTH_ALT})\s*,?\s+(\d{{4}})(?!\d)")
_MON_D_Y = re.compile(rf"({_MONTH_ALT})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s+(\d{{4}})(?!\d)")
_MON_Y = re.compile(rf"(?<![\w])({_MONTH_ALT})\s*,?\s+(\d{{4}})(?!\d)")
_YEAR_CUED = re.compile(r"(?:\ben\b|\bin\b|\bdurant\b|\bduring\b|\bannee\b|\bsince\b|\bdepuis\b|في|سنه|عام|سنة|منذ)\s+(\d{4})(?!\d)")


@dataclass(frozen=True)
class ExtractedDate:
    date: date          # first day of the span for month/year precision
    precision: str      # 'day' | 'month' | 'year'
    start: int
    end: int
    raw: str

    @property
    def span_end(self) -> date:
        if self.precision == "day":
            return self.date
        if self.precision == "month":
            return self.date + relativedelta(months=1) - timedelta(days=1)
        return date(self.date.year, 12, 31)


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract_dates(text: str) -> list[ExtractedDate]:
    t = normalize(text)
    found: list[ExtractedDate] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    def add(m: re.Match, d: date | None, prec: str) -> None:
        if d and free(m.start(), m.end()):
            taken.append((m.start(), m.end()))
            found.append(ExtractedDate(d, prec, m.start(), m.end(), m.group(0)))

    for m in _ISO.finditer(t):
        add(m, _safe(int(m[1]), int(m[2]), int(m[3])), "day")
    for m in _D_MON_Y.finditer(t):
        add(m, _safe(int(m[3]), MONTHS[m[2]], int(m[1])), "day")
    for m in _MON_D_Y.finditer(t):
        add(m, _safe(int(m[3]), MONTHS[m[1]], int(m[2])), "day")
    for m in _DMY.finditer(t):  # Moroccan convention: day first
        add(m, _safe(int(m[3]), int(m[2]), int(m[1])), "day")
    for m in _MON_Y.finditer(t):
        add(m, _safe(int(m[2]), MONTHS[m[1]], 1), "month")
    for m in _YEAR_CUED.finditer(t):
        add(m, _safe(int(m[1]), 1, 1), "year")
    return sorted(found, key=lambda d: d.start)


_REL = [
    (re.compile(r"\b(?:aujourd'hui|today|now|maintenant)\b|اليوم|الان"), lambda t: t),
    (re.compile(r"\b(?:hier|yesterday)\b|البارحه|امس"), lambda t: t - timedelta(days=1)),
    (re.compile(r"semaine derniere|last week|الاسبوع الماضي|الاسبوع الفايت"), lambda t: t - timedelta(days=7)),
    (re.compile(r"mois dernier|last month|الشهر الماضي|الشهر الفايت"), lambda t: t - relativedelta(months=1)),
    (re.compile(r"annee derniere|l'an dernier|last year|السنه الماضيه|العام الماضي|العام الفايت|السنه الفايته"), lambda t: t - relativedelta(years=1)),
]


def resolve_relative(text: str, today: date) -> date | None:
    """Resolve phrases such as 'last week' from the DEVICE clock, never from model memory."""
    t = normalize(text)
    for rx, fn in _REL:
        if rx.search(t):
            return fn(today)
    return None


def to_iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None
