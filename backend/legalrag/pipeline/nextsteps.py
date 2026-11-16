"""What to do next: when the user describes his own situation, the answer ends with practical steps.

The steps are written by the model from the SAME articles the answer quotes (plus the calculators' results and how the Court
of Cassation decided similar cases), then checked in code before anything is shown:
- a step may only cite passages it was given; invented ids are removed;
- a step that states a time limit, or contains any number, must cite a passage, and every number must be found in the passages
  it cites, in the question or in a calculator result: otherwise the step is dropped (no invented deadlines or amounts);
- steps that only organise the person (gather the papers, keep the proof) may stand without an article, as long as they contain no number.
A general question ("what is the notice period?") gets no steps. Without a model nothing is added."""
from __future__ import annotations

import re
from typing import Any

from ..llm.providers import GenRequest
from ..text.arabic import normalize, numbers_in, tokens

# the person speaks about himself or someone close: "طردني", "زوجي", "عندي", "j'ai", "mon employeur", "my landlord"
_PERSONAL = re.compile(
    r"(?:ني|تني|ونا|لي|عندي|عندنا|ديالي|ديالنا|انا|نحن|زوجي|زوجتي|ابي|امي|اخي|اختي|ابني|ابنتي|ولدي|بنتي|مشغلي|جاري|صاحب (?:العمل|الدار|المحل))(?=\s|$|[.,،؟?!])"
    r"|\b(?:j'|je |j ai|m'a|m'ont|nous |mon |ma |mes |notre |nos )"
    r"|\b(?:i |i'm|i've|my |me |we |our )", re.I)
_SITUATION = re.compile(r"نزاع|مشكل|خلاف|طرد|فصل|رفض|امتنع|هدد|ضرب|اعتد|توقف|لم يؤد|لم يدفع|ما خلص|توفي|مات|طلق|حكم|تبليغ|انذار|شكاي|دعوى|كراء|افراغ|حادث"
                        r"|litige|conflit|problème|probleme|licenci|renvoy|refus|menac|frapp|impay|décéd|deced|divorc|jugement|plainte|expuls|accident|loyer|dette"
                        r"|dispute|problem|fired|dismiss|refus|threat|evict|unpaid|died|divorc|judg|sued|complaint|accident|rent|debt", re.I)

SYSTEM = """You are the last part of a Moroccan law assistant. The person described a real situation and already received an answer made of
verified statements from the law. Write what this person can DO next, concretely, in the order to do it. Return JSON only.

Rules:
- If the question is general (asks what the law says, without a personal situation), return {"is_case": false, "steps": []}.
- 3 to 6 steps. Each step is ONE action the person can take: who does what, where (which court, office or authority, as the passages name it),
  with which papers, and within which time limit. Start the title with a verb. Plain words a non-lawyer understands.
- Use ONLY the supplied passages, calculator results and rulings. Every step that states a right, a time limit, an amount, a court or an authority
  must list in "passages" the ids of the passages that say so. Never give a number (days, months, dirhams, percentages) that is not written in a
  passage you cite or in a calculator result. If the passages do not give the time limit, write that it must be checked with the clerk's office.
- Put the most urgent step first (a time limit that is running, a protection measure, keeping proof).
- "documents": the papers and proof to gather for that step (may be empty).
- Use what the similar rulings show only to say what the Court looked at (e.g. what had to be proved): never promise a result.
- Do not repeat the answer. Do not invent names: keep the placeholders exactly as written (e.g. [PERSON_1]).
- "professional": one sentence saying when a lawyer (or adoul, notary, labour inspector, as fits) is needed for this situation.
- Write in the language given in "language"."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_case": {"type": "boolean"},
        "steps": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "text": {"type": "string"}, "deadline": {"type": "string"}, "where": {"type": "string"},
                "documents": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "passages": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "text", "passages"],
        }},
        "professional": {"type": "string"},
    },
    "required": ["is_case", "steps"],
}


def is_case(text: str) -> bool:
    """A personal situation, not a question about the law in general."""
    t = normalize(text)
    if len(tokens(text)) < 6:
        return False
    return bool((_PERSONAL.search(t) or _PERSONAL.search(text)) and (_SITUATION.search(t) or _SITUATION.search(text) or len(tokens(text)) >= 18))


def _nums(*texts: str) -> set[str]:
    out: set[str] = set()
    for t in texts:
        out.update(numbers_in(t or ""))
    return out


def build(llm, *, question: str, lang: str, as_of: str, claims: list[str], passages: dict[str, dict[str, str]],
          calcs: list[str], rulings: dict[str, Any] | None, case_id: str | None, scan: bool = True) -> dict[str, Any] | None:
    """-> {"steps": [...], "professional": str} with pseudonyms still in place, or None.
    passages: id -> {"source": "<law> - <article>", "text": ...} (the ones the answer was written from)."""
    if llm is None or not passages:
        return None
    payload = {
        "language": lang, "law_date": as_of, "situation": question, "verified_answer": claims,
        "passages": [{"id": k, "source": p["source"], "text": p["text"][:1800]} for k, p in passages.items()],
        "calculator_results": calcs,
        "similar_rulings": None if not rulings else {
            "outcomes_among_most_similar": rulings.get("by_outcome"),
            "examples": [{"outcome": r.get("outcome"), "principle": r.get("principle")} for r in rulings.get("items", [])]},
    }
    got = llm.generate_json(GenRequest(SYSTEM, payload, SCHEMA, [question] if scan else [], case_id, kind="next_steps"))
    if not isinstance(got, dict) or not got.get("is_case"):
        return None
    free = _nums(question, *calcs)                       # numbers the person gave, or a calculator computed
    steps = []
    for st in got.get("steps") or []:
        if not isinstance(st, dict):
            continue
        title, text = str(st.get("title") or "").strip(), str(st.get("text") or "").strip()
        if not title or not text:
            continue
        ids = [p for p in dict.fromkeys(st.get("passages") or []) if p in passages]
        deadline, where = str(st.get("deadline") or "").strip(), str(st.get("where") or "").strip()
        docs = [str(d).strip() for d in (st.get("documents") or []) if str(d).strip()][:8]
        said = _nums(title, text, deadline, where, *docs)
        known = free | _nums(*(passages[p]["text"] + " " + passages[p]["source"] for p in ids))
        if (said - known) or (deadline and not ids):       # a number no cited article contains, or a time limit with no article
            continue
        steps.append({"title": title[:160], "text": text[:900], "deadline": deadline[:200], "where": where[:200], "documents": docs, "sources": ids})
    if len(steps) < 2:                                     # one surviving step is not a plan
        return None
    return {"steps": steps[:6], "professional": str(got.get("professional") or "").strip()[:400]}
