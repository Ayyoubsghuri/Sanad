"""On-device pseudonymisation: detect -> typed placeholders -> encrypted vault -> restore after verification."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..store.userdb import UserDB
from ..text.arabic import normalize
from . import names as N
from .patterns import DIRECT_IDENTIFIER_KINDS, Span, detect_patterns, resolve_overlaps

_PLACEHOLDER = re.compile(r"\[(?:PERSON|CIN|PHONE|EMAIL|RIB|ICE|COMPANYID|ADDRESS|CASE|DOB|PLATE|ORG)_\d+\]")
_TITLE_STRIP = re.compile(r"^(?:m\.?|mr|mme|mlle|monsieur|madame|mademoiselle|me|maitre|dr|pr)\s+", re.I)


@dataclass
class Entity:
    placeholder: str
    kind: str
    start: int  # position in the OUTPUT text
    end: int
    origin: str


@dataclass
class PseudoResult:
    text: str
    entities: list[Entity] = field(default_factory=list)
    confidence: float = 1.0
    warnings: list[str] = field(default_factory=list)
    unknown_tokens: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def placeholders(self) -> list[str]:
        return sorted({e.placeholder for e in self.entities})


def find_placeholders(text: str) -> list[str]:
    return _PLACEHOLDER.findall(text or "")


def _key(kind: str, original: str) -> str:
    n = normalize(original)
    if kind in ("PERSON", "ORG", "ADDRESS"):
        n = _TITLE_STRIP.sub("", n)
        return re.sub(r"\s+", " ", n).strip()
    return re.sub(r"[^0-9a-z؀-ۿ]", "", n)  # identifiers: ignore spaces/dashes/dots


# Public legal references are never personal data: "قرار 1432.26", "المرسوم رقم 2.24.865", "الفصل 214", "article 3 de la loi 10.23".
# The PII model tags such numbers as IDENTIFIER and the rules can see a case number in "القرار رقم 666.25"; masked, the question loses
# the law it names (the search then answers from unrelated texts).  A detection that overlaps one of these references is dropped,
# except words the user marked himself.  Court file numbers ("ملف عدد 1234/2020") have slashes, not dots, and stay masked.
_KIND = (r"(?:القانون\s+التنظيمي|قانون\s+تنظيمي|القانون|قانون|المرسوم\s+بقانون|مرسوم\s+بقانون|المرسوم|مرسوم|الظهير\s+الشريف|ظهير\s+شريف|الظهير|ظهير|"
         r"القرار\s+المشترك|قرار\s+مشترك|القرار|قرار|المقرر|مقرر|الدورية|دورية|المنشور|منشور|loi\s+organique|loi|d[ée]cret|dahir|arr[êe]t[ée]|circulaire|law|decree|order)")
_LAW_REF = re.compile(_KIND + r"(?:\s+[^\d\s]{2,20}){0,6}?\s*(?:رقم|عدد|n°|no\.?|num[ée]ro)?\s*:?\s*(?P<num>\d+(?:\.\d+)+)", re.I)
_ART_REF = re.compile(r"(?:الفصل|الفصول|المادة|المواد|فصل|مادة|articles?|art\.)\s*(?:رقم|n°|no\.?)?\s*(?P<num>\d{1,4})(?![\d/])", re.I)


# The PII model sometimes takes a public institution for a person or a private company ("بنك" in "بنك المغرب" came back as PERSON).
# A model detection that STARTS with one of these head words is a public body named by the law, not personal data.  Only the model's
# detections are filtered: names the user marked, the names list and the rules are untouched.
_INSTITUTION_HEADS = {normalize(w) for w in (
    "بنك", "البنك", "مجلس", "المجلس", "وزارة", "الوزارة", "وزير", "الوزير", "محكمة", "المحكمة", "صندوق", "الصندوق", "مكتب", "المكتب", "وكالة",
    "الوكالة", "هيئة", "الهيئة", "مديرية", "المديرية", "الخزينة", "خزينة", "المندوبية", "مندوبية", "القرض", "قرض", "جامعة", "الجامعة", "معهد",
    "المعهد", "أكاديمية", "الأكاديمية", "مركز", "المركز", "جماعة", "الجماعة", "عمالة", "ولاية", "جهة", "الحكومة", "حكومة", "البرلمان", "مجلس النواب",
    "المملكة", "المغرب", "الجريدة", "مؤسسة", "المؤسسة", "سلطة", "السلطة", "النيابة", "رئاسة", "رئيس", "المجموعة", "الشركة الوطنية", "الإدارة",
    "إدارة", "المفتشية", "مفتشية", "الديوان", "ديوان", "الأمانة", "الكتابة", "المحافظة", "الصندوق الوطني", "banque", "conseil", "ministere", "ministère",
    "tribunal", "cour", "fonds", "office", "agence", "haut-commissariat", "direction", "tresorerie", "trésorerie", "royaume", "gouvernement",
)}


def _public_body(text: str) -> bool:
    toks = normalize(text).split()
    return bool(toks) and (toks[0] in _INSTITUTION_HEADS or " ".join(toks[:2]) in _INSTITUTION_HEADS)


def public_reference_spans(text: str) -> list[tuple[int, int]]:
    """Spans of the NUMBERS of public references only: a name written between "قرار" and its number is still masked."""
    return [m.span("num") for rx in (_LAW_REF, _ART_REF) for m in rx.finditer(text)]


class Pseudonymiser:
    def __init__(self, db: UserDB, names: N.NameData | None = None, ner=None):
        self.db = db
        self.ner = ner  # optional NerDetector (Arabic PII model)
        self.nd = names or N.load_names()

    # ------------------------------------------------------------------------------------------
    def detect(self, text: str, case_id: str, *, keep_places: bool = True, extra_terms: list[tuple[str, str]] | None = None, use_ner: bool = True) -> tuple[list[Span], list[str]]:
        spans = detect_patterns(text)
        name_spans, unknown = N.detect_names(text, self.nd)
        spans += name_spans
        terms = list(self.db.marked_terms()) + list(extra_terms or [])
        spans += N.find_terms(text, terms, "user")
        if self.ner is not None and use_ner:
            spans += [sp for sp in self.ner.detect(text) if not _public_body(text[sp.start:sp.end])]
        # entities already known in this case (also catches bare surnames / partial mentions)
        case_terms: list[tuple[str, str]] = []
        for _ph, (kind, original) in self.db.vault_all(case_id).items():
            case_terms.append((original, kind))
            if kind in ("PERSON", "ORG"):
                case_terms += [(tok, kind) for tok in re.split(r"\s+", original) if len(tok) >= 3 and normalize(tok) not in self.nd.particles]
        spans += N.find_terms(text, case_terms, "case")
        if not keep_places:
            spans += N.find_places(text, self.nd)
        protected = public_reference_spans(text)
        if protected:
            spans = [sp for sp in spans if sp.origin == "user" or not any(sp.start < e and b < sp.end for b, e in protected)]
        final = resolve_overlaps(spans)
        # unknown capitalised words that ended up inside a replaced span are not a residual risk
        still_unknown = [w for (w, st) in unknown if not any(s.start <= st < s.end for s in final)]
        return final, still_unknown

    def pseudonymise(
        self,
        text: str,
        case_id: str,
        *,
        keep_places: bool = True,
        extra_terms: list[tuple[str, str]] | None = None,
        doc_like: bool = False,
        use_ner: bool = True,
    ) -> PseudoResult:
        spans, unknown = self.detect(text, case_id, keep_places=keep_places, extra_terms=extra_terms, use_ner=use_ner)
        out: list[str] = []
        ents: list[Entity] = []
        pos = 0
        out_len = 0
        counts: dict[str, int] = {}
        for sp in spans:
            original = text[sp.start:sp.end]
            ph = self._placeholder(case_id, sp.kind, original)
            chunk = text[pos:sp.start]
            out.append(chunk)
            out_len += len(chunk)
            ents.append(Entity(ph, sp.kind, out_len, out_len + len(ph), sp.origin))
            out.append(ph)
            out_len += len(ph)
            pos = sp.end
            counts[sp.kind] = counts.get(sp.kind, 0) + 1
        out.append(text[pos:])
        res = PseudoResult("".join(out), ents, 1.0, [], unknown, counts)
        self._score(res, text, doc_like)
        return res

    # ------------------------------------------------------------------------------------------
    def _placeholder(self, case_id: str, kind: str, original: str) -> str:
        key = _key(kind, original)
        h = self.db.keys.blind_index(f"{kind}|{key}")
        found = self.db.vault_find(case_id, kind, h)
        if found:
            return found
        aliases: list[str] = []
        if kind in ("PERSON", "ORG"):
            for tok in key.split():
                if len(tok) >= 3 and tok not in self.nd.particles:
                    ah = self.db.keys.blind_index(f"{kind}|{tok}")
                    if not self.db.vault_find(case_id, kind, ah):
                        aliases.append(ah)
        return self.db.vault_add(case_id, kind, original.strip(), h, aliases)

    @staticmethod
    def _score(res: PseudoResult, original: str, doc_like: bool) -> None:
        score = 1.0
        if res.unknown_tokens:
            score -= min(0.6, 0.08 * len(res.unknown_tokens))
            res.warnings.append(f"{len(res.unknown_tokens)} capitalised word(s) not recognised as names or legal terms: review before sending")
        if doc_like and len(original) > 200 and N_arabic(original) and not res.counts.get("PERSON") and not res.counts.get("ORG"):
            score -= 0.15
            res.warnings.append("no person names were detected in a long Arabic document; names may have been missed")
        res.confidence = round(max(0.0, score), 3)

    # ------------------------------------------------------------------------------------------
    def restore(self, text: str, case_id: str) -> tuple[str, list[str]]:
        """Swap placeholders back to originals. Returns (restored text, placeholders not in the vault)."""
        vault = self.db.vault_all(case_id)
        unknown: list[str] = []

        def sub(m: re.Match) -> str:
            ph = m.group(0)
            if ph in vault:
                return vault[ph][1]
            unknown.append(ph)
            return ph

        return _PLACEHOLDER.sub(sub, text), unknown

    def known_placeholders(self, case_id: str) -> set[str]:
        return set(self.db.vault_all(case_id))

    def mark_missed(self, term: str, kind: str = "PERSON") -> None:
        self.db.add_marked_term(term, kind)


def N_arabic(text: str) -> bool:
    from ..text.arabic import arabic_ratio

    return arabic_ratio(text) > 0.5


def direct_identifier_kinds() -> set[str]:
    return set(DIRECT_IDENTIFIER_KINDS)
