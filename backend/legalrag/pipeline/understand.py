"""Step 2-5 of the query flow, rule-based and on-device: language, as-of date, question type, domains, sub-questions,
exact citations, premise check, scope/risk flags. (An optional structured cloud call can enrich this; the rules are
always the floor.) Relative dates ("last week") use the DEVICE clock."""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date

from ..services import terms as terms_svc
from ..store.lawpack import LawPack
from ..text import stopwords
from ..text.arabic import normalize, numbers_in, tokens
from ..text.citations import CitationRef, laws_named, parse_citations
from ..text.dates import ExtractedDate, extract_dates, resolve_relative
from ..text.lang import detect_language

_RX = lambda p: re.compile(p, re.I)  # noqa: E731
CALC_WORDS = _RX(r"calcul|combien|how much|compute|احسب|حساب|شحال|كم يبلغ|montant")
PROC_WORDS = _RX(r"d[ée]lai|appel|pourvoi|proc[ée]dure|deadline|appeal|time limit|الأجل|اجل|استئناف|الطعن|مسطرة|اجال|آجال")
DRAFT_WORDS = _RX(r"r[ée]dige|draft (me|a)|write (me )?a (contract|letter)|صياغة|حرر لي|اكتب لي")
DOC_WORDS = _RX(r"document ci-joint|attached (document|file)|ce document|this document|هذه الوثيقة|المستند المرفق")
NON_MA = _RX(r"droit fran[cç]ais|french law|code civil fran|loi fran[cç]aise|القانون الفرنسي|spanish law|droit espagnol|القانون الاسباني|القانون الإسباني|english law|uk law|us law|القانون الامريكي|القانون الأمريكي|القانون المصري|egyptian law|droit alg[ée]rien|القانون الجزائري")
IMMINENT = _RX(r"demain|tomorrow|غدا|غدًا|urgent|dernier jour|last day|آخر أجل|اخر اجل|today is the deadline|expire (aujourd|today)|ينتهي اليوم")
CRIMINAL = _RX(r"garde [àa] vue|arrest|police|prison|p[ée]nal|criminal|جنائي|جنحة|الحراسة النظرية|سجن|اعتقال|شرطة|poursuite|plainte p[ée]nale|جناية")
CUSTODY = _RX(r"garde des enfants|child custody|custody|حضانة|droit de visite|visitation|الحضانة")
# facts of a case already under way: only then is "on what date was it filed?" a question worth stopping for
CASE_FACTS = _RX(r"رفعت|رفعنا|رفع علي|صدر (?:ضدي|في حقي|علي)|حكم (?:ضدي|علي)|بلغت|تم تبليغي|توصلت|توصلنا|j'ai (?:re[cç]u|d[ée]pos[ée]|[ée]t[ée] (?:notifi|condamn))|on m'a (?:notifi|signifi)|jugement (?:rendu|prononc)|decision rendered|i was (?:served|notified|sued)|i (?:filed|received a (?:judgment|notice))")
SENTENCE_SPLIT = re.compile(r"[?؟\n;]+")

REFERRALS = {
    "non_moroccan_law": {"en": "This tool covers Moroccan law only. For foreign law consult a qualified professional in that jurisdiction.", "fr": "Cet outil ne couvre que le droit marocain. Pour un droit étranger, consultez un professionnel qualifié de la juridiction concernée.", "ar": "تغطي هذه الأداة القانون المغربي فقط. بالنسبة لقانون أجنبي يرجى استشارة مختص مؤهل في ذلك البلد."},
    "imminent_deadline": {"en": "A deadline may be imminent. Consult a lawyer or the clerk's office today; do not rely on this tool alone.", "fr": "Un délai semble imminent. Consultez dès aujourd'hui un avocat ou le greffe ; ne vous fiez pas uniquement à cet outil.", "ar": "قد يكون هناك أجل وشيك. استشر محاميا أو كتابة الضبط اليوم ولا تعتمد على هذه الأداة وحدها."},
    "criminal": {"en": "Criminal matters carry serious consequences: consult a lawyer before acting.", "fr": "Les affaires pénales ont des conséquences graves : consultez un avocat avant d'agir.", "ar": "للقضايا الجنائية عواقب جسيمة: استشر محاميا قبل أي إجراء."},
    "custody": {"en": "Custody and family matters depend on the facts of each case: consult a lawyer or the family court.", "fr": "La garde et les affaires familiales dépendent des faits de chaque dossier : consultez un avocat ou le tribunal de la famille.", "ar": "تتوقف الحضانة وقضايا الأسرة على وقائع كل ملف: استشر محاميا أو قسم قضاء الأسرة."},
    "drafting": {"en": "This tool does not draft contracts or letters; it quotes the law. Consult a legal professional for drafting.", "fr": "Cet outil ne rédige pas de contrats ni de courriers : il cite la loi. Consultez un professionnel pour la rédaction.", "ar": "لا تقوم هذه الأداة بصياغة العقود أو الرسائل، بل تستشهد بالقانون. استشر مختصا للصياغة."},
}
CLARIFY = {
    "filing_date": {"en": "On what date was the case filed (or the decision rendered)? The applicable rule depends on it.", "fr": "À quelle date l'affaire a-t-elle été introduite (ou la décision rendue) ? La règle applicable en dépend.", "ar": "في أي تاريخ رفعت الدعوى (أو صدر الحكم)؟ القاعدة المطبقة تتوقف على ذلك."},
    "which_date": {"en": "Which date should the law be applied on? Several dates appear in your question.", "fr": "À quelle date faut-il appliquer la loi ? Plusieurs dates figurent dans votre question.", "ar": "في أي تاريخ يجب تطبيق القانون؟ ورد أكثر من تاريخ في سؤالك."},
    "exact_day": {"en": "The law changed during the period you mention. What is the exact date?", "fr": "La loi a changé pendant la période mentionnée. Quelle est la date exacte ?", "ar": "تغير القانون خلال الفترة المذكورة. ما هو التاريخ بالتحديد؟"},
    "too_vague": {"en": "Please give me a precise legal question about Moroccan law, for example: “What is the time limit to appeal a civil judgment?” or “What does article 2 of the Labour Code say?”.", "fr": "Précisez votre question juridique sur le droit marocain, par exemple : « Quel est le délai d'appel d'un jugement civil ? » ou « Que dit l'article 2 du Code du travail ? ».", "ar": "من فضلك اطرح سؤالا قانونيا محددا حول القانون المغربي، مثلا: «ما هو أجل استئناف حكم مدني؟» أو «ماذا ينص الفصل 2 من مدونة الشغل؟»."},
    "greeting": {"en": "Hello! Ask me a precise legal question about Moroccan law, for example: “What is the time limit to appeal a civil judgment?” or “What does article 2 of the Labour Code say?”.", "fr": "Bonjour ! Posez-moi une question juridique précise sur le droit marocain, par exemple : « Quel est le délai d'appel d'un jugement civil ? » ou « Que dit l'article 2 du Code du travail ? ».", "ar": "مرحبا! اطرح علي سؤالا قانونيا محددا حول القانون المغربي، مثلا: «ما هو أجل استئناف حكم مدني؟» أو «ماذا ينص الفصل 2 من مدونة الشغل؟»."},
    "law_unclear": {"en": "Which law do you mean by this article?", "fr": "De quelle loi s'agit-il pour cet article ?", "ar": "أي قانون تقصد بهذه المادة؟"},
}


# greetings / thanks / tests: there is nothing to look up, and a one-word query must never be "answered" by whatever passage contains that word
SMALLTALK = re.compile(
    r"^\W*(hi+|hello+|hey+|hola|salut|bonjour|bonsoir|coucou|salam+|salaam|slm|wesh|merci|thanks?|thank you|ok|okay|test|yo|good (morning|evening)|"
    r"اختبار|سلام|السلام عليكم|مرحبا|مرحبا بك|أهلا|اهلا|أهلا وسهلا|شكرا|شكرًا|صباح الخير|مساء الخير|هلا|واش|لاباس)\W*$", re.I)


def _is_too_vague(text: str, has_refs: bool, has_terms: bool) -> bool:
    if SMALLTALK.match(text.strip()):
        return True
    content = [t for t in tokens(text) if t not in stopwords.ALL and len(t) > 1]
    return len(content) < 2 and not has_refs and not has_terms and not numbers_in(text)


def msg(table: dict, key: str, lang: str) -> str:
    d = table[key]
    return d.get({"darija": "ar"}.get(lang, lang), d["en"])


@dataclass
class Understanding:
    lang: str
    as_of: date
    as_of_source: str  # request | text | relative | default
    as_of_assumption: str
    question_type: str
    domains: list[str]
    sub_questions: list[str]
    exact_refs: list[CitationRef]
    flags: list[str]
    clarification: str | None
    clarification_kind: str | None
    date_candidates: list[str]
    premise_warnings: list[dict] = field(default_factory=list)
    calculator_hints: list[str] = field(default_factory=list)
    question_numbers: set[str] = field(default_factory=set)
    focus_instruments: list[str] = field(default_factory=list)
    period: tuple | None = None  # (start, end, precision) of a month/year named in the question


def _qtype(text: str) -> str:
    if DRAFT_WORDS.search(text):
        return "drafting"
    if DOC_WORDS.search(text):
        return "document_review"
    if PROC_WORDS.search(normalize(text)) or PROC_WORDS.search(text):
        return "procedure"
    if CALC_WORDS.search(text):
        return "calculation"
    return "lookup"


def _calc_hints(entries: list[dict], qtype: str) -> list[str]:
    ids = {e["id"] for e in entries}
    hints = []
    if "min_wage" in ids or ("wage" in ids and qtype == "calculation"):
        hints.append("minimum_wage")
    if "severance" in ids or ("dismissal" in ids and qtype == "calculation"):
        hints.append("severance")
    if "registration_duty" in ids:
        hints.append("registration_cash_surcharge")
    if "inheritance" in ids:
        hints.append("inheritance_shares")
    if qtype == "procedure" or "appeal" in ids or "deadline" in ids:
        hints.append("procedural_deadline")
    if "limitation" in ids:
        hints.append("limitation_period")
    if ids & {"vat", "income_tax", "corporate_tax"}:
        hints.append("tax_computation")
    return list(dict.fromkeys(hints))


def split_sub_questions(text: str, limit: int) -> list[str]:
    parts = [p.strip(" .,:") for p in SENTENCE_SPLIT.split(text) if len(tokens(p)) >= 3]
    return parts[:limit] if len(parts) > 1 else []


def understand(
    text: str,
    pack: LawPack | None,
    *,
    today: date,
    explicit_as_of: date | None = None,
    as_of_declined: bool = False,
    max_sub: int = 4,
    context_instrument: str | None = None,
) -> Understanding:
    lang = detect_language(text)
    dates = extract_dates(text)
    rel = resolve_relative(text, today)
    entries = terms_svc.match_entries(text)
    domains = list(dict.fromkeys(e["domain"] for e in entries))
    qtype = _qtype(text)
    flags = [k for k, rx in (("non_moroccan_law", NON_MA), ("imminent_deadline", IMMINENT), ("criminal", CRIMINAL), ("custody", CUSTODY)) if rx.search(text) or rx.search(normalize(text))]
    if qtype == "drafting":
        flags.append("drafting")

    clarification = kind = None
    candidates = [d.date.isoformat() for d in dates]
    period: tuple | None = None
    if explicit_as_of:
        as_of, src, note = explicit_as_of, "request", f"law applied as in force on {explicit_as_of.isoformat()} (chosen by the user)"
    elif len(dates) == 1 and dates[0].precision == "day":
        as_of, src, note = dates[0].date, "text", f"law applied as in force on {dates[0].date.isoformat()} (date found in the question)"
    elif len(dates) == 1 and dates[0].precision == "year":
        # "نسبة العجز سنة 2024": the year is what the question is ABOUT; figures for a year are published in later texts.  The law in force
        # today is used (it still contains the texts of that year), and the answer says so.  Whether an article found for the question
        # changed during that year is checked after the search, on those articles only.
        d0 = dates[0]
        as_of, src, note = today, "text_year", f"the year {d0.date.year} is read as the subject of the question: texts in force today are used, later ones included; give an exact date to apply the law as it stood then"
        period = (d0.date, min(d0.span_end, today), "year")
    elif len(dates) == 1:
        d0 = dates[0]
        as_of, src, note = d0.date, "text", f"law applied as in force on {d0.date.isoformat()} (start of {d0.raw})"
        period = (d0.date, d0.span_end, d0.precision)  # "exact_day" is asked after the search, only if one of ITS articles changed in that month
    elif len(dates) > 1:
        as_of, src, note = max(d.date for d in dates), "text", "several dates in the question; the latest was used"
        if not as_of_declined:
            clarification, kind = msg(CLARIFY, "which_date", lang), "which_date"
    elif rel:
        as_of, src, note = rel, "relative", f"law applied as in force on {rel.isoformat()} (resolved from the device clock)"
    else:
        as_of, src, note = today, "default", f"no date given: law applied as in force today ({today.isoformat()})"
        if qtype == "procedure" and not as_of_declined:
            if CASE_FACTS.search(text) or CASE_FACTS.search(normalize(text)):
                clarification, kind = msg(CLARIFY, "filing_date", lang), "filing_date"
            else:  # a general question about a procedure or a time limit: answer with today's law and say what to add for a case under way
                note += {"en": " · if a case is already under way, give the filing date or the decision date: the rule may differ",
                         "fr": " · si une affaire est déjà en cours, indiquez la date d'introduction ou de la décision : la règle peut différer",
                         "ar": " · إن كانت هناك قضية جارية فاذكر تاريخ رفعها أو صدور الحكم، فقد تختلف القاعدة"}.get(lang, "")

    refs = parse_citations(text, pack.aliases(), pack.instrument_ids()) if pack is not None else []
    if context_instrument and refs and not any(r.instrument_id for r in refs):  # "and article 215?": the law of the previous answer
        refs = [dataclasses.replace(r, instrument_id=context_instrument) for r in refs]
    if refs and any(r.instrument_id is None for r in refs) and clarification is None:
        clarification, kind = msg(CLARIFY, "law_unclear", lang), "law_unclear"
    if _is_too_vague(text, bool(refs), bool(entries)):
        k = "greeting" if SMALLTALK.match(text.strip()) else "too_vague"
        clarification, kind = msg(CLARIFY, k, lang), k
    return Understanding(
        lang=lang, as_of=as_of, as_of_source=src, as_of_assumption=note, question_type=qtype, domains=domains,
        sub_questions=split_sub_questions(text, max_sub), exact_refs=refs, flags=flags, clarification=clarification, clarification_kind=kind,
        date_candidates=candidates, calculator_hints=_calc_hints(entries, qtype), question_numbers=set(numbers_in(text)),
        focus_instruments=laws_named(text, pack.instrument_ids()) if pack is not None else [], period=period,
    )


def check_premises(text: str, u: Understanding, pack: LawPack) -> list[dict]:
    """"Article 30 says 15 days": verify the asserted numbers against the pack before answering (sycophancy guard)."""
    warnings: list[dict] = []
    nt = normalize(text)
    for ref in u.exact_refs:
        if not ref.instrument_id:
            continue
        pid = pack.find_provision(ref.instrument_id, ref.number, ref.suffix)
        ver = pack.version_at(pid, u.as_of) if pid else None
        if not ver:
            continue
        sentence = next((s for s in re.split(r"[.?!؟\n]+", nt) if ref.raw in s), "")
        asserted = {n for n in numbers_in(sentence)} - {str(ref.number)} - {str(d.year) for d in extract_dates(sentence) for d in [d.date]}
        if not asserted:
            continue
        actual = set()
        for t in pack.texts(ver["pv_id"]).values():
            actual |= set(numbers_in(t["text"]))
        wrong = sorted(n for n in asserted if n not in actual)
        if wrong:
            warnings.append({"reference": ref.raw, "provision_id": pid, "asserted_numbers": wrong,
                             "note": "the number(s) you state do not appear in the text of this article on the as-of date; check the quoted text"})
    return warnings
