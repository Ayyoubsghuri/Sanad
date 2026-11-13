"""Write what happened in the last question(s) to a file, to see WHY an answer is the way it is.

    py tools\\last_answer.py            -> reports\\last_answer.json  (the last question)
    py tools\\last_answer.py 3          -> the last 3

Contains: the sub-questions the planner made, the deep-search rounds, every passage retrieved with its score, and EVERY claim the model wrote,
including the ones the checker removed and why.  The question text is included only if "store question text" is on in the settings
(it is already pseudonymised)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalrag.config import Settings  # noqa: E402
from legalrag.state import build_context  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ctx = build_context(Settings())
rows = ctx.db.list_traces(n)
out = [dict(ctx.db.get_trace(r["trace_id"]) or {}, created_at=r["created_at"]) for r in rows]
for t in out:
    t.pop("sources_snapshot", None)
dest = Path(__file__).resolve().parent.parent / "reports" / "last_answer.json"
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(out if n > 1 else (out[0] if out else {}), ensure_ascii=False, indent=1, default=str), "utf-8")
print("written:", dest)
for t in out:
    print(f"  answer of {t.get('created_at')}  status={t.get('status')}  sub-questions={len(t.get('sub_questions') or [])}  trace={t.get('trace_id')}")
if out:
    from datetime import datetime, timezone
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(out[0].get("created_at")))).total_seconds() / 60
        if age > 5:
            print(f"  NOTE: the newest answer is {age:.0f} minutes old: ask the question again (after restarting the backend) before running this.")
    except ValueError:
        pass
