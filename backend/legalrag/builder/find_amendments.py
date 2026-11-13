"""Which laws in the pack amend a base code after the date the code's text was consolidated?

    py -m legalrag.builder.find_amendments batches/codes.json            (report; also writes reports/amendments_report.json)

For every code in the batch file it looks in the installed law pack for texts that (a) are dated after the code's `consolidated_on`,
(b) name the code (by its law number or its title) next to an amending verb (تغيير / تتميم / نسخ / تعويض / إلغاء / تعديل),
and prints the article numbers they say they touch.  It changes nothing: it is the list you (or the next step) work from.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

VERBS = r"(?:بتغيير|تغيير|بتتميم|تتميم|بنسخ|نسخ|بتعويض|تعويض|بإلغاء|إلغاء|بتعديل|تعديل|المغير|المتمم|المعدل)"
ART = re.compile(r"(?:المواد|الفصول|المادة|الفصل)\s+([\d\s,،وإلى\-–]+?)(?=\s*(?:من|$|[^\d\s,،وإلى\-–]))")


def amendments(db: sqlite3.Connection, entry: dict) -> list[dict]:
    num = str(entry.get("number") or "")
    title = entry.get("title") or ""
    since = entry.get("consolidated_on") or entry.get("effective") or "0000-00-00"
    keys = [k for k in {title, f"رقم {num}" if re.search(r"\d+\.\d+$", num) else ""} if k]
    if not keys:
        return []
    rows = db.execute(
        "SELECT i.instrument_id, i.number, i.title_ar, i.bo_number, i.bo_date, i.promulgation_date "
        "FROM instrument i WHERE COALESCE(i.bo_date, i.promulgation_date, '') > ? AND i.instrument_id NOT LIKE ?",
        (since, f"%{num}%")).fetchall()
    out: list[dict] = []
    for iid, n, t, bo, bod, prom in rows:
        texts = [r[0] for r in db.execute(
            "SELECT pt.text FROM provision p JOIN provision_version pv USING(provision_id) JOIN provision_text pt USING(pv_id) "
            "WHERE p.instrument_id=? AND pt.lang='ar'", (iid,))]
        head = " ".join(filter(None, [t or ""])) + " " + " ".join(texts[:6])
        if not any(k in head for k in keys):
            continue
        if not re.search(VERBS, head):
            continue
        touched = sorted({m.group(1).strip() for m in ART.finditer(head)})[:12]
        out.append({"instrument_id": iid, "number": n, "title": t, "bo_number": bo, "bo_date": bod or prom, "articles_mentioned": touched})
    return sorted(out, key=lambda r: r["bo_date"] or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("batch")
    ap.add_argument("--db", help="pack file (default: the app's current pack)")
    ap.add_argument("--out", default="reports/amendments_report.json")
    a = ap.parse_args(argv)
    if a.db:
        path = Path(a.db)
    else:
        from ..config import Settings
        path = Settings().resolved_lawpack_path()
    if not path.exists():
        print("pack not found:", path)
        return 2
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    entries = [e for e in json.loads(Path(a.batch).read_text("utf-8")) if e.get("number")]
    report = {}
    for e in entries:
        found = amendments(db, e)
        report[e["number"]] = {"title": e.get("title"), "after": e.get("consolidated_on"), "amending_texts": found}
        print(f"\n{e['number']} {e.get('title')}  (text consolidated {e.get('consolidated_on')}): {len(found)} amending text(s) in the pack")
        for r in found:
            print(f"   {r['bo_date']}  BO {r['bo_number']}  {r['number']}  {(r['title'] or '')[:70]}  -> {'; '.join(r['articles_mentioned'][:4])}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    print("\nwritten:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
