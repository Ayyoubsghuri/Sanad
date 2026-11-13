"""Show what the search does for one question:  py tools\\probe.py "ما هي ساعات العمل القانونية في المغرب؟" [--find LAW_65.99:184]"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from legalrag.config import Settings
from legalrag.pipeline import understand as U
from legalrag.retrieval.engine import RetrievalRequest
from legalrag.state import build_context

ap = argparse.ArgumentParser(); ap.add_argument("query"); ap.add_argument("--find"); a = ap.parse_args()
ctx = build_context(Settings())
u = U.understand(a.query, ctx.pack, today=ctx.today_fn(), explicit_as_of=ctx.today_fn(), max_sub=ctx.settings.max_subquestions)
print("understood: domains=%s focus=%s exact_refs=%s sub_questions=%s flags=%s" % (u.domains, u.focus_instruments, u.exact_refs, u.sub_questions, getattr(u, "flags", None)))
r = ctx.engine.retrieve(RetrievalRequest(query=a.query, as_of=ctx.today_fn(), sub_questions=u.sub_questions, domains=u.domains, exact_refs=u.exact_refs,
                                         focus_instruments=u.focus_instruments, today=ctx.today_fn(), lang="ar", keep=40))
c = r.coverage
print("coverage: covered=%s top=%.3f margin=%.3f supports=%s reason=%s" % (c.covered, c.top_score, c.margin, c.supports, c.reason))
print("notes:", r.notes, "| modes:", r.modes_used, "| candidates:", len(r.candidates))
for i, k in enumerate(sorted(r.candidates, key=lambda k: -k.score), 1):
    m = k.chunk
    mark = "  <==" if a.find and f"{m.instrument_id}:{m.number}".startswith(a.find) else ""
    print(f"{i:2} {m.instrument_id:18} art.{m.number:8} score={k.score:.3f} dense#{k.dense_rank} bm25#{k.bm25_rank} {k.source:10} {m.body[:70]!r}{mark}")
