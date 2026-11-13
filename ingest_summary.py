"""Usage:  py ingest_summary.py C:\\path\\ingest_report.json   -> what was skipped / warned / refused, in plain counts."""
import json, re, sys
from collections import Counter

r = json.load(open(sys.argv[1], encoding="utf-8"))
ing, chk = r["ingest"], r["checks"]
print(f"instruments {ing['instruments']}  articles {ing['articles']}  issues {ing['issues']}")
print("\n== CHECK ERRORS (build refuses while any) ==")
for e in chk["errors"]:
    print(" ", e.get("code"), "|", e.get("where"), "|", str(e.get("detail"))[:160])
print("\n== check warnings by code ==")
for k, n in Counter(w.get("code") for w in chk["warnings"]).most_common(): print(f"  {n:6d}  {k}")
print("\n== skipped blocks by reason ==")
c = Counter(re.sub(r"[:(].*", "", s["reason"]).strip() for s in ing["skipped"])
for k, n in c.most_common(): print(f"  {n:6d}  {k}")
print("\n== skipped: the 'broken_arabic_order' files (must be re-extracted) ==")
bad = sorted({s["file"] for s in ing["skipped"] if s["reason"].startswith("broken_arabic_order")})
print(" ", len(bad), "files", bad[:15])
print("\n== ingest warnings by code ==")
for k, n in Counter(w.get("code") for w in ing["warnings"]).most_common(): print(f"  {n:6d}  {k}")
print("\n== examples of skipped 'number not readable' / 'no readable date' ==")
for key in ("number not readable", "no readable date"):
    ex = [s for s in ing["skipped"] if s["reason"].startswith(key)][:4]
    for s in ex: print(" ", key, "|", s.get("file"), "|", (s.get("title") or "")[:90])
