"""What to do next: when the user describes his own situation, the answer ends with a plan built from everything found.

Inputs: the articles the answer was written from, the articles on time limits found by a dedicated search in the same laws,
the calculators' results, and the most similar Court of Cassation rulings (their outcome, principle and grounds).
Output, all checked in code before anything is shown:
- court_insights: 1-2 plain sentences on what the Court decided in similar cases. Each must name a ruling it was given;
  a number in it must appear in that ruling, in the question or in a calculator result.
- steps: 3-6 actions in order. A step may cite only the articles and rulings it was given (invented ids are removed); a step
  with a time limit and no article is removed; a number found neither in its cited articles or rulings, nor in the question,
  nor in a calculator result removes the step. Steps that only organise the person (gather the papers) may stand without a
  source, as long as they contain no number.
- to_clarify: the facts the person did not give that change the result (type of contract, reason given...). No numbers.
A general question ("what is the notice period?") gets no plan. Without a model nothing is added."""
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
# an article about a time limit or limitation: worth giving to the plan even if the answer did not use it
DEADLINE_WORDS = re.compile(r"أجل|آجال|اجل|تقادم|يتقادم|يسقط|سقوط|داخل\s+أجل|يوما|يوم\s+من|شهر\s+من|délai|prescri|forclusion|time limit", re.I)

SYSTEM = """You are the last part of a Moroccan law assistant. The person described a real situation and already received an answer made of
verified statements from the law. Using EVERYTHING you are given (the law passages, the passages on time limits, the calculator results and the
similar Court of Cassation rulings), write the plan this person should follow. Return JSON only.

Rules:
- If the question is general (asks what the law says, without a personal situation), return {"is_case": false, "steps": []}.
- court_insights: 0 to 2 short sentences in plain words saying what the Court of Cassation decided in the similar rulings that matters for THIS
  person (e.g. what had to be proved, what gave the right to compensation, what made the appeal fail). Each lists in "rulings" the ids (R1, R2...)
  it comes from. Only from what the rulings say; never promise a result; skip a ruling about a different situation.
- steps: 3 to 6, in the order to do them, the most URGENT first: a time limit that is running (if a passage on time limits applies, say it and
  cite it), protecting proof, then the procedure. Each step is ONE concrete action: who does what, where (the court, office or authority the
  passages name), with which papers. Start the title with a verb. Plain words a non-lawyer understands.
  "passages": ids of the law passages it rests on; "rulings": ids of the rulings it rests on (e.g. a step to keep proof of what the Court required).
- A time limit, an amount, a court or an authority may appear only if a passage or ruling you cite states it. Never give a number (days, months,
  dirhams, percentages) that is not written in what you cite, in the question or in a calculator result. If no passage gives the time limit, write
  in "deadline" that it must be checked with the clerk's office. Leave "deadline" and "where" empty when they do not apply (no filler).
- "documents": the papers and proof to gather for that step (may be empty).
- to_clarify: 0 to 4 facts the person did not give that would change what applies (e.g. the type of contract, the reason the employer gave).
  Short questions to ask oneself, no numbers.
- "professional": one sentence saying when a lawyer (or adoul, notary, labour inspector, as fits) is needed for this situation.
- Do not repeat the answer. Do not invent names: keep the placeholders exactly as written (e.g. [PERSON_1]).
- Write in the language given in "language"."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_case": {"type": "boolean"},
        "court_insights": {"type": "array", "maxItems": 2, "items": {
            "type": "object", "properties": {"text": {"type": "string"}, "rulings": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "rulings"]}},
        "steps": {"type": "array", "maxItems": 6, "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}, "text": {"type": "string"}, "deadline": {"type": "string"}, "where": {"type": "string"},
                "documents": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
                "passages": {"type": "array", "items": {"type": "string"}},
                "rulings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title", "text", "passages"],
        }},
        "to_clarify": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
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


def _ruling_text(r: dict[str, Any]) -> str:
    g = " ".join(f"{x.get('ground', '')} {x.get('answer', '')}" for x in r.get("grounds") or [])
    return f"{r.get('number') or ''} {r.get('date') or ''} {r.get('full_principle') or r.get('principle') or ''} {g}"


_FILLER = {normalize(x) for x in ("عندك", "عندي", "في البيت", "في منزلك", "لا يوجد", "لا ينطبق", "غير محدد", "chez vous", "chez soi", "aucun",
                                     "néant", "sans objet", "at home", "none", "n/a", "na", "-", "—")}


def _filler(s: str) -> bool:
    """"عندك", "n/a", "-": not a place or a time limit."""
    t = normalize(s).strip(" .،,:;")
    return len(t) < 3 or t in _FILLER


def build(llm, *, question: str, lang: str, as_of: str, claims: list[str], passages: dict[str, dict[str, str]],
          calcs: list[str], rulings: dict[str, Any] | None, case_id: str | None, scan: bool = True,
          deadline_ids: list[str] | None = None) -> dict[str, Any] | None:
    """-> {"steps", "court_insights", "to_clarify", "professional"} with pseudonyms still in place, or None.
    passages: id -> {"source": "<law> - <article>", "text": ...}; deadline_ids: the passages found by the time-limit search."""
    if llm is None or not passages:
        return None
    items = (rulings or {}).get("items") or []
    rmap = {f"R{i}": r for i, r in enumerate(items, start=1)}
    dl = set(deadline_ids or [])
    payload = {
        "language": lang, "law_date": as_of, "situation": question, "verified_answer": claims,
        "passages": [{"id": k, "source": p["source"], "text": p["text"][:1800]} for k, p in passages.items() if k not in dl],
        "passages_on_time_limits": [{"id": k, "source": p["source"], "text": p["text"][:1800]} for k, p in passages.items() if k in dl],
        "calculator_results": calcs,
        "similar_rulings": [{"id": rid, "outcome": r.get("outcome"), "applies_articles": r.get("applies") or [], "date": r.get("date"),
                             "principle": r.get("full_principle") or r.get("principle"), "grounds": r.get("grounds") or []}
                            for rid, r in rmap.items()],
        "outcomes_among_most_similar_rulings": (rulings or {}).get("by_outcome"),
    }
    got = llm.generate_json(GenRequest(SYSTEM, payload, SCHEMA, [question] if scan else [], case_id, kind="next_steps"))
    if not isinstance(got, dict) or not got.get("is_case"):
        return None
    free = _nums(question, *calcs)                       # numbers the person gave, or a calculator computed
    ref = lambda rid: {"ruling_id": rmap[rid].get("ruling_id"), "number": rmap[rid].get("number"), "date": rmap[rid].get("date")}  # noqa: E731

    insights = []
    for x in got.get("court_insights") or []:
        if not isinstance(x, dict) or not str(x.get("text") or "").strip():
            continue
        rids = [r for r in dict.fromkeys(x.get("rulings") or []) if r in rmap]
        text = str(x["text"]).strip()
        if not rids or _nums(text) - (free | _nums(*(_ruling_text(rmap[r]) for r in rids))):
            continue                                     # a statement on no given ruling, or a number none of them contains
        insights.append({"text": text[:500], "rulings": [ref(r) for r in rids]})

    steps = []
    for st in got.get("steps") or []:
        if not isinstance(st, dict):
            continue
        title, text = str(st.get("title") or "").strip(), str(st.get("text") or "").strip()
        if not title or not text:
            continue
        ids = [p for p in dict.fromkeys(st.get("passages") or []) if p in passages]
        rids = [r for r in dict.fromkeys(st.get("rulings") or []) if r in rmap]
        deadline, where = str(st.get("deadline") or "").strip(), str(st.get("where") or "").strip()
        deadline, where = ("" if _filler(deadline) else deadline), ("" if _filler(where) else where)
        docs = [str(d).strip() for d in (st.get("documents") or []) if str(d).strip()][:8]
        said = _nums(title, text, deadline, where, *docs)
        known = free | _nums(*(passages[p]["text"] + " " + passages[p]["source"] for p in ids)) | _nums(*(_ruling_text(rmap[r]) for r in rids))
        if (said - known) or (deadline and not ids and not rids and _nums(deadline)):
            continue                                     # a number nothing cited contains, or a dated time limit with no source
        steps.append({"title": title[:160], "text": text[:900], "deadline": deadline[:200], "where": where[:200], "documents": docs,
                      "sources": ids, "rulings": [ref(r) for r in rids]})
    if len(steps) < 2:                                   # one surviving step is not a plan
        return None
    clarify = [c.strip()[:200] for c in got.get("to_clarify") or [] if isinstance(c, str) and c.strip() and not (_nums(c) - free)][:4]
    return {"steps": steps[:6], "court_insights": insights, "to_clarify": clarify,
            "professional": str(got.get("professional") or "").strip()[:400]}
