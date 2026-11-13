"""python -m legalrag.diagnose "<question>" [--as-of YYYY-MM-DD]

Runs ONE question against the installed law pack, offline-safe, and prints what the search sees: the language and date it understood,
the laws it recognised by number, the number of passages it searched inside them, the best candidates with their scores, and why the
answer was or was not allowed.  Nothing is sent anywhere; no language model is called."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from .config import Settings
from .retrieval.engine import RetrievalRequest
from .pipeline import understand as U
from .state import build_context


def diagnose(ctx, question: str, as_of: date | None = None, top: int = 10, subs: list[str] | None = None) -> dict:
    """Same path as the app: the question is masked first (rules + the PII model), then understood and searched."""
    pack = ctx.pack
    today = ctx.today_fn()
    original = question
    question = ctx.pseudo.pseudonymise(question, ctx.db.create_case(), keep_places=ctx.user_settings()["keep_places"]).text
    u = U.understand(question, pack, today=today, explicit_as_of=as_of, max_sub=ctx.settings.max_subquestions)
    req = RetrievalRequest(query=question, as_of=u.as_of, sub_questions=(subs or u.sub_questions), domains=u.domains, exact_refs=u.exact_refs,
                           focus_instruments=u.focus_instruments, today=today, lang="ar" if u.lang == "darija" else u.lang)
    ret = ctx.engine.retrieve(req)
    return {
        "masked_question": question, "masking_changed_it": question != original,
        "understood": {"language": u.lang, "as_of": u.as_of.isoformat(), "clarification": u.clarification_kind, "exact_refs": [r.raw for r in u.exact_refs],
                       "named_laws": u.focus_instruments},
        "named_law_passages": len(ret.focus_chunk_ids),
        "modes": ret.modes_used, "notes": ret.notes,
        "coverage": vars(ret.coverage),
        "all_candidates": [{"chunk": c.chunk.chunk_id, "score": round(c.score, 3)} for c in ret.candidates],
        "candidates": [{"provision": c.chunk.provision_id, "chunk": c.chunk.chunk_id, "score": round(c.score, 3), "source": c.source,
                        "in_named_law": c.chunk.chunk_id in ret.focus_chunk_ids, "text": c.chunk.body[:90].replace("\n", " ")} for c in ret.candidates[:top]],
    }


def find_phrase(ctx, phrase: str, cand_scores: dict[int, float], limit: int = 15) -> list[dict]:
    """Every passage of the pack whose text contains `phrase` (as written), and the score it got for the question (None = not among the
    candidates the search kept).  Shows whether an answer is missing from the pack or present but ranked too low."""
    rows = ctx.pack._q("SELECT c.chunk_id, pv.provision_id, substr(c.body, 1, 110) AS head FROM chunk c JOIN provision_version pv ON pv.pv_id=c.pv_id "
                       "WHERE c.body LIKE ? LIMIT ?", (f"%{phrase}%", limit))
    return [{"chunk": r["chunk_id"], "provision": r["provision_id"], "score": cand_scores.get(r["chunk_id"]), "text": r["head"].replace("\n", " ")} for r in rows]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m legalrag.diagnose")
    ap.add_argument("question")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--sub", action="append", default=[], help="a sub-question, as the planner would write it (can be repeated)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--find", action="append", default=[], help="a phrase to look for in the whole pack (can be repeated)")
    a = ap.parse_args(argv)
    ctx = build_context(Settings())
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    d = diagnose(ctx, a.question, date.fromisoformat(a.as_of) if a.as_of else None, a.top, a.sub or None)
    u = d["understood"]
    print(f"question after masking: {d['masked_question']}" + ("   <-- CHANGED by the masking" if d["masking_changed_it"] else "   (unchanged)"))
    print(f"language={u['language']}  law date={u['as_of']}  clarification={u['clarification']}")
    print(f"exact article references: {u['exact_refs'] or 'none'}")
    print(f"laws recognised by number: {u['named_laws'] or 'NONE'}  ->  {d['named_law_passages']} passages searched inside them")
    print(f"search modes: {d['modes']}")
    for n in d["notes"]:
        print("note:", n)
    c = d["coverage"]
    print(f"coverage: covered={c['covered']} top_score={c['top_score']:.3f} reason={c['reason']}")
    print("best candidates (score, provision, in the named law?):")
    for x in d["candidates"]:
        print(f"  {x['score']:.3f}  {x['provision']}  {'*' if x['in_named_law'] else ' '}  {x['text']}")
    scores = {x["chunk"]: x["score"] for x in d["all_candidates"]}
    for ph in a.find:
        hits = find_phrase(ctx, ph, scores)
        print(f"\npassages of the pack containing \"{ph}\": {len(hits)}{' (first 15)' if len(hits) == 15 else ''}")
        for h in hits:
            sc = "not kept by the search" if h["score"] is None else f"score {h['score']:.3f}"
            print(f"  {h['provision']}  [{sc}]  {h['text']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
