"""Deeper search (the "agent"), switched on by the Deep / Maximum thinking budget in the app.

A bounded loop, never free-running:  judge the passages found so far -> if something the question asks is missing, search again with
the queries the judge proposes -> merge -> judge again (at most `rounds` times).  The judge only decides WHAT TO SEARCH FOR; it never
writes the answer, never lowers the coverage rule, and every quote of the final answer is still checked by code.  Without a language
model (offline mode, no key) nothing here runs and the normal single search is used.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from ..llm.providers import GenRequest
from ..retrieval.engine import Candidate, RetrievalRequest, RetrievalResult
from ..verify import renderer

ROUNDS = {"deep": 2, "max": 3}
JUDGED = 8  # passages shown to the judge
SNIPPET = 420  # characters of each
NEW_PER_QUERY = 4

JUDGE_SYSTEM = """You help a search engine over Moroccan legal texts decide whether it has found what a question needs.
You are given a question and the passages found so far (numbered). Judge ONLY from these passages. Do not answer the question.
Return JSON: {"verdict": "enough" | "partial" | "none", "missing": "<what the question asks that no passage gives, or empty>", "queries": ["<new search query>", ...]}.
- "enough": the passages together contain what is needed to answer every part of the question.
- "partial": some parts are covered, others not. "none": nothing relevant.
- queries: at most 3, only when not "enough". Each is a SHORT search phrase in the language of the legal text (usually Arabic) built from the vocabulary the law would use
  (e.g. "سحب الأوراق البنكية من التداول" for "when do old banknotes stop being valid"), aimed at the missing part. Never repeat the question; never invent names, numbers or dates.
- Laws rarely use everyday words: they state general categories and file rules under chapter headings. So ONE query must be the legal category or the
  heading the law would file the topic under, not the everyday word. Examples: marrying an aunt -> "موانع الزواج المؤبدة المحرمات بالقرابة";
  which rights are real rights -> "الحقوق العينية الأصلية"; age when custody ends -> "مدة الحضانة"; firing a worker -> "إنهاء عقد الشغل الفصل".
- A passage that mentions the everyday word only in another context (e.g. "الجمع بين امرأة وعمتها" for marrying the aunt herself) does not answer the question: say "partial"."""

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["enough", "partial", "none"]},
        "missing": {"type": "string"},
        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["verdict", "queries"],
}


def _view(pack, cands: list[Candidate], lang: str, as_of) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(cands[:JUDGED], start=1):
        e = renderer.source_entry(pack, c, lang, as_of, f"C{c.chunk.chunk_id}")
        out.append({"n": i, "source": f"{e['law']}, {e['article']}", "text": (e["chunk_text"] or e["text"])[:SNIPPET]})
    return out


def _merge(res: RetrievalResult, extra: RetrievalResult, taken: set[int]) -> list[int]:
    """Add the best NEW passages of `extra` (search hits that pass the normal relevance bar) to `res`."""
    have = {c.chunk.chunk_id for c in res.candidates} | {c.chunk.pv_id * -1 for c in res.candidates}
    added: list[int] = []
    for c in sorted(extra.candidates, key=lambda c: -c.score):
        if len(added) >= NEW_PER_QUERY:
            break
        if c.source not in ("search", "exact") or c.chunk.chunk_id in have or -c.chunk.pv_id in have:
            continue
        if c.score <= 0:
            continue
        res.candidates.append(c)
        have.add(c.chunk.chunk_id)
        have.add(-c.chunk.pv_id)
        added.append(c.chunk.chunk_id)
        taken.add(c.chunk.chunk_id)
    return added


def run(ctx, llm, rreq: RetrievalRequest, res: RetrievalResult, *, depth: str, lang: str, scan_question: bool, pg=None) -> dict[str, Any]:
    """Improves `res` in place; returns a trace for the answer ("research")."""
    rounds_max = ROUNDS.get(depth, 0)
    trace: dict[str, Any] = {"depth": depth, "rounds": []}
    if not rounds_max or llm is None:
        return trace
    from .progress import _Noop

    pg = pg or _Noop()
    pack, engine = ctx.pack, ctx.engine
    tried = {rreq.query}
    taken: set[int] = set()
    for rnd in range(1, rounds_max + 1):
        cands = [c for c in res.candidates if c.source in ("exact", "search")] or res.candidates
        cands = sorted(cands, key=lambda c: -c.score)
        view = _view(pack, cands, lang, rreq.as_of)
        entry: dict[str, Any] = {"round": rnd}
        st = pg.start(f"Deep search · round {rnd}: checking what was found", "thinking", f"{len(view)} passage(s) read by the model")
        try:
            out = llm.generate_json(GenRequest(JUDGE_SYSTEM, {"question": rreq.query, "passages": view}, JUDGE_SCHEMA, [rreq.query] if scan_question else [], rreq.case_id, kind="research"))
        except Exception as e:  # noqa: BLE001 - a provider error never breaks the question: the normal search result stands
            entry["error"] = e.__class__.__name__
            trace["rounds"].append(entry)
            pg.done(st, f"the model could not be reached ({e.__class__.__name__}): the normal search result is used")
            break
        verdict = (out or {}).get("verdict") if isinstance((out or {}).get("verdict"), str) else "enough"
        queries = [q.strip() for q in ((out or {}).get("queries") or []) if isinstance(q, str) and 3 <= len(q.strip()) <= 200 and q.strip() not in tried][:3]
        entry.update(verdict=verdict, missing=str((out or {}).get("missing") or "")[:300], queries=queries, added=[])
        trace["rounds"].append(entry)
        label = {"enough": "enough to answer", "partial": "partly covered", "none": "nothing relevant yet"}.get(verdict, verdict)
        pg.done(st, f"verdict: {label}" + (f"\nmissing: {entry['missing']}" if entry["missing"] else "") + (f"\nnew searches: " + " | ".join(queries) if queries else ""))
        if verdict == "enough" or not queries:
            break
        st2 = pg.start(f"Deep search · round {rnd}: searching again", "search", " | ".join(queries))
        for q in queries:
            tried.add(q)
            try:
                extra = engine.retrieve(dataclasses.replace(rreq, query=q, sub_questions=[], exact_refs=[], focus_instruments=[], expand=False, keep=6))
            except Exception:  # noqa: BLE001
                continue
            entry["added"] += _merge(res, extra, taken)
        found = [renderer.source_entry(pack, c, lang, rreq.as_of, "x") for c in res.candidates if c.chunk.chunk_id in entry["added"]]
        pg.done(st2, (f"{len(entry['added'])} new passage(s):\n" + "\n".join(f"{e['law']}, {e['article']}" for e in found)) if found else "nothing new found")
        if not entry["added"]:
            break
    if taken:
        res.candidates = engine._authority_order(res.candidates)  # noqa: SLF001 - same presentation order as a normal search
        # the question is now judged on the best passage of the enlarged set (the normal relevance bar still applies)
        best = max((c.score for c in res.candidates if c.source in ("search", "exact")), default=0.0)
        if not res.coverage.covered and best >= ctx.settings.coverage_min_top_score:
            res.coverage.covered, res.coverage.reason, res.coverage.top_score = True, None, best
            res.coverage.supports = max(res.coverage.supports, sum(1 for c in res.candidates if c.score >= ctx.settings.coverage_min_top_score * 0.8))
        res.notes.append(f"deep search: {sum(len(r.get('added', [])) for r in trace['rounds'])} more passage(s) found in {len(trace['rounds'])} round(s)")
    return trace
