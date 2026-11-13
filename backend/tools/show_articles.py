"""Print articles of a law from the pack:  py tools\\show_articles.py LAW_52.05 18 98 102 184"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from legalrag.config import Settings
from legalrag.state import build_context
from legalrag.services import tools as T

ctx = build_context(Settings())
pack, iid = ctx.pack, sys.argv[1]
print(iid, "-", (pack.instrument(iid) or {}).get("title_ar"))
for num in sys.argv[2:]:
    m = re.match(r"(\d+)(-\d+)?", num)
    for ed in reversed(T.family(pack, iid)):
        pid = pack.find_provision(ed, int(m.group(1)), m.group(2) or "")
        v = pid and pack.version_at(pid, ctx.today_fn())
        if v:
            t = pack.texts(v["pv_id"])
            print(f"\n--- art. {num} ({ed}) ---\n" + (t.get("ar") or next(iter(t.values()), {"text": ""}))["text"][:600])
            break
    else:
        print(f"\n--- art. {num}: not found ---")
