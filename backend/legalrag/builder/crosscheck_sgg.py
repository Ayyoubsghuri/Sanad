"""Compare the SGG consolidated texts with what the pack already holds from the Bulletin Officiel.

    py -m legalrag.builder.crosscheck_sgg data/sgg            (report only; writes reports/crosscheck_report.json)

Nothing is installed or changed.  For each SGG file the law is found in the pack by its number (22_80.md -> 22.80, 1_58_377.md -> 1.58.377),
both are cut into articles, and each article pair is compared.  Per law you get: articles only in the SGG text (the BO issues you hold do not
have them), articles only in the pack, and articles whose wording differs -- with the first lines of both so you can see why.
Differences are normal when the SGG text is consolidated later than the pack's text (a later amendment); what matters is the list.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sqlite3
import sys
from pathlib import Path

from ..text.arabic import normalize
from .from_law_pdf import clean_pages, read_pages, split_articles


def number_from_name(stem: str) -> str:
    return stem.replace("_", ".")


def _norm(t: str) -> str:
    t = normalize(t or "")
    t = re.sub(r"[\d\W_]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def pack_articles(db: sqlite3.Connection, number: str) -> tuple[str | None, dict[str, str]]:
    row = db.execute("SELECT instrument_id FROM instrument WHERE number=? OR number=? ORDER BY instrument_id LIMIT 1", (number, number.lstrip("0"))).fetchone()
    if not row:
        return None, {}
    iid = row[0]
    arts: dict[str, str] = {}
    q = ("SELECT p.number, p.suffix, pt.text FROM provision p JOIN provision_version pv USING(provision_id) JOIN provision_text pt USING(pv_id) "
         "WHERE p.instrument_id=? AND pv.valid_to IS NULL")
    for n, sfx, text in db.execute(q, (iid,)):
        key = str(n) if (not sfx or str(n).endswith(str(sfx))) else f"{n} {sfx}"
        arts[key.strip()] = text
    return iid, arts


def sgg_articles(path: Path) -> dict[str, str]:
    pages, _ = read_pages(path)
    lines, _ = clean_pages(pages)
    arts, _ = split_articles(lines, "ar")
    if len(arts) < 3:
        arts, _ = split_articles(lines, "fr")
    return {a.number: a.body for a in arts}


def compare(sgg: dict[str, str], pack: dict[str, str], same: float = 0.90) -> dict:
    only_sgg = [n for n in sgg if n not in pack]
    only_pack = [n for n in pack if n not in sgg]
    differ = []
    for n in sgg:
        if n in pack:
            a, b = _norm(sgg[n]), _norm(pack[n])
            r = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0
            if r < same:
                differ.append({"article": n, "similarity": round(r, 2), "sgg": sgg[n][:160], "pack": pack[n][:160]})
    return {"only_sgg": only_sgg, "only_pack": only_pack, "differ": sorted(differ, key=lambda d: d["similarity"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--db")
    ap.add_argument("--out", default="reports/crosscheck_report.json")
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
    report: dict = {}
    not_in_pack: list[str] = []
    for f in sorted(Path(a.folder).rglob("*.md")):
        num = number_from_name(f.stem)
        iid, pk = pack_articles(db, num)
        if not iid:
            not_in_pack.append(num)
            continue
        try:
            sg = sgg_articles(f)
        except Exception as ex:  # noqa: BLE001
            print(f"{num}: could not read ({ex.__class__.__name__})")
            continue
        c = compare(sg, pk)
        report[num] = {"instrument": iid, "sgg_articles": len(sg), "pack_articles": len(pk), **c}
        print(f"{num:12} sgg={len(sg):4} pack={len(pk):4} only-sgg={len(c['only_sgg']):3} only-pack={len(c['only_pack']):3} differ={len(c['differ']):3}")
    print(f"\nnot in the pack at all ({len(not_in_pack)}): {', '.join(not_in_pack)}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps({"compared": report, "not_in_pack": not_in_pack}, ensure_ascii=False, indent=1), "utf-8")
    print("written:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
