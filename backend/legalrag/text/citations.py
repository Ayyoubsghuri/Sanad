"""Parse exact legal references ("الفصل 230 من ق.ل.ع", "article 30 CPC", "art. 5 bis du Code ...")
and resolve them against the instrument alias table of the law pack."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .arabic import compact_acronyms, normalize

_ART_WORDS = r"(?:articles?|art\.?|الفصل|الفصول|المادة|الماده|المواد|فصل|مادة|ماده)"
_SUFFIX = r"(?:\s*(?:bis|ter|quater|quinquies|مكرر|ثالثا|رابعا))?"
_ART_RX = re.compile(rf"(?<!\w){_ART_WORDS}\s*(?:n°|no\.?|رقم)?\s*(\d{{1,4}})((?:\s*[-–]\s*\d{{1,3}}){{0,2}}){_SUFFIX}(?!\d)")
_SUFFIX_MAP = {"bis": "bis", "ter": "ter", "quater": "quater", "quinquies": "quinquies", "مكرر": "bis", "ثالثا": "ter", "رابعا": "quater"}
_WINDOW = 48


@dataclass(frozen=True)
class CitationRef:
    instrument_id: str | None
    number: int
    suffix: str
    raw: str
    start: int
    end: int
    alias: str | None = None

    @property
    def label(self) -> str:
        if self.suffix.startswith("-"):
            return f"{self.number}{self.suffix}"
        return f"{self.number}{(' ' + self.suffix) if self.suffix else ''}"


# "الفصل 214 من القانون 10.23", "article 3 du décret n° 2.24.865": the law is named by its kind and number, exactly how the bulletin
# instruments are identified (<CODE>_<number>), so no alias table is needed for the thousands of texts read from the BO.
_KIND_WORDS = [
    ("القانون التنظيمي", "ORG"), ("قانون تنظيمي", "ORG"), ("loi organique", "ORG"),
    ("الظهير الشريف", "DAHIR"), ("ظهير شريف", "DAHIR"), ("الظهير", "DAHIR"), ("ظهير", "DAHIR"), ("dahir", "DAHIR"),
    ("المرسوم بقانون", "DECLAW"), ("مرسوم بقانون", "DECLAW"),
    ("المرسوم", "DECREE"), ("مرسوم", "DECREE"), ("decret", "DECREE"), ("decree", "DECREE"),
    ("القانون", "LAW"), ("قانون", "LAW"), ("loi", "LAW"), ("law", "LAW"),
    ("القرار", "ORDER"), ("قرار", "ORDER"), ("arrete", "ORDER"), ("order", "ORDER"),
    ("الدورية", "CIRC"), ("دورية", "CIRC"), ("circulaire", "CIRC"),
]
_CODE_OF = dict(_KIND_WORDS)
_NUMBERED_RX = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(w) for w, _ in sorted(_KIND_WORDS, key=lambda kw: -len(kw[0]))) + r")\s*(?:رقم|n°|no\.?|numero|num|number|n)?\s*(\d+(?:[.\-/]\d+)*)"
)


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", s).strip("-")


_LOOKUP_CACHE: dict[int, tuple[int, dict[str, list[str]]]] = {}


def _lookup_all(known_ids: set[str]) -> dict[str, list[str]]:
    """"<CODE>_<digits only>" -> instrument ids, best first (no _BO republication suffix, then shortest).  normalize/compact_acronyms drop the
    dots of "10.23", so numbers are compared without separators."""
    c = _LOOKUP_CACHE.get(id(known_ids))
    if c and c[0] == len(known_ids):
        return c[1]
    out: dict[str, list[str]] = {}
    for iid in sorted(known_ids, key=lambda i: ("_BO" in i, len(i), i)):
        code, _, num = iid.partition("_")
        out.setdefault(f"{code}_{re.sub(r'[^0-9]', '', num.split('_BO')[0])}", []).append(iid)
    _LOOKUP_CACHE.clear()
    _LOOKUP_CACHE[id(known_ids)] = (len(known_ids), out)
    return out


def _lookup(known_ids: set[str]) -> dict[str, str]:
    return {k: v[0] for k, v in _lookup_all(known_ids).items()}


# Arabic glues prepositions and "and" to the word: "بالمرسوم رقم 2.24.1008", "للقانون 10.23", "وبالفصل 5", "والمادة 3".  The kind words and
# article words are matched alone, so the proclitics are removed first (on the normalised text, where ة is ه).
_LEGAL_HEADS = r"(?:قانون|مرسوم|ظهير|قرار|مقرر|دوريه|منشور|فصل|فصول|ماده|مواد)"
_PROCLITIC_AL = re.compile(r"(?<!\w)[وف]?[بك](?=ال" + _LEGAL_HEADS + r")")
_PROCLITIC_LL = re.compile(r"(?<!\w)[وف]?لل(?=" + _LEGAL_HEADS + r")")
_PROCLITIC_W = re.compile(r"(?<!\w)[وف](?=ال" + _LEGAL_HEADS + r")")


def strip_proclitics(t: str) -> str:
    t = _PROCLITIC_LL.sub("ال", t)
    t = _PROCLITIC_AL.sub("", t)
    return _PROCLITIC_W.sub("", t)


def laws_named(text: str, known_ids: set[str], limit: int = 3) -> list[str]:
    """Laws the question names by kind and number ("المرسوم 2.25.966", "la loi 10.23"), every republication included.  No article needed."""
    lk = _lookup_all(known_ids)
    t = strip_proclitics(compact_acronyms(normalize(text)))
    out: list[str] = []
    for m in _NUMBERED_RX.finditer(t):
        for iid in lk.get(f"{_CODE_OF[m.group(1)]}_{re.sub(r'[^0-9]', '', m.group(2))}", []):
            if iid not in out:
                out.append(iid)
    return out[: limit * 3]


def _numbered_law(segment: str, known_ids: set[str], from_end: bool) -> tuple[int, str] | None:
    """-> (distance to the article mention, instrument_id) of the nearest "<kind> <number>" in the segment that is an instrument of the pack."""
    lk = _lookup(known_ids)
    best = None
    for m in _NUMBERED_RX.finditer(segment):
        iid = lk.get(f"{_CODE_OF[m.group(1)]}_{re.sub(r'[^0-9]', '', m.group(2))}")
        if iid:
            dist = (len(segment) - m.end()) if from_end else m.start()
            if best is None or dist < best[0]:
                best = (dist, iid)
    return best


def prep_alias(alias: str) -> str:
    return compact_acronyms(normalize(alias))


def parse_citations(text: str, aliases: dict[str, str], instrument_ids: set[str] | None = None) -> list[CitationRef]:
    """`aliases` maps alias text -> instrument_id. Unresolved article mentions are returned with
    instrument_id=None so the caller can ask which law is meant."""
    t = strip_proclitics(compact_acronyms(normalize(text)))
    prepared = sorted(((prep_alias(a), iid) for a, iid in aliases.items() if a), key=lambda x: -len(x[0]))
    refs: list[CitationRef] = []
    for m in _ART_RX.finditer(t):
        suffix = ""
        num = int(m.group(1))
        plural = bool(re.match(r"(?:articles|الفصول|المواد)", m.group(0)))  # "المواد 3 - 5": a range, not article 3-5
        dash = [] if plural else [int(x) for x in re.findall(r"\d+", m.group(2) or "")]
        if dash:
            # "المادة 78-2" (an article added after 78).  A text layer can flip it ("1-78"): the base is the larger number when the first is small
            if len(dash) == 1 and num < dash[0] and dash[0] >= 10 and num <= 30:
                num, dash = dash[0], [num]
            suffix = "".join(f"-{d}" for d in dash)
        sm = re.search(r"(bis|ter|quater|quinquies|مكرر|ثالثا|رابعا)\s*$", m.group(0))
        if sm and not suffix:
            suffix = _SUFFIX_MAP[sm.group(1)]
        after = t[m.end(): m.end() + _WINDOW]
        before = t[max(0, m.start() - _WINDOW): m.start()]
        best: tuple[int, str, str] | None = None  # (distance, alias, iid)
        for a, iid in prepared:
            rx = re.compile(rf"(?<!\w){re.escape(a)}(?!\w)")
            ma = rx.search(after)
            if ma and (best is None or ma.start() < best[0]):
                best = (ma.start(), a, iid)
            mb = None
            for mb in rx.finditer(before):
                pass
            if mb is not None:
                dist = len(before) - mb.end()
                if best is None or dist < best[0]:
                    best = (dist, a, iid)
        if best is None and instrument_ids:
            cands = [c for c in (_numbered_law(after, instrument_ids, False), _numbered_law(before, instrument_ids, True)) if c]
            if cands:
                d, iid = min(cands)
                best = (d, "", iid)
        refs.append(
            CitationRef(best[2] if best else None, num, suffix, m.group(0), m.start(), m.end(), (best[1] or None) if best else None)
        )
    return refs


def provision_id_for(instrument_id: str, number: int, suffix: str = "") -> str:
    """Convention used by the pack builder: <INSTRUMENT>_ART_<n>[_<suffix>]; an added article "78-2" is <INSTRUMENT>_ART_78-2."""
    if suffix.startswith("-"):
        return f"{instrument_id}_ART_{number}{suffix}"
    return f"{instrument_id}_ART_{number}" + (f"_{suffix.upper()}" if suffix else "")
