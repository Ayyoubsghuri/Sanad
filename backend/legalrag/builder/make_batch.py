"""Write a batch file for a folder of SGG consolidated texts (Lois / Decrets / Lois_organiques, one .md per text).

    py -m legalrag.builder.make_batch data/sgg --out batches/sgg.json

Number, kind, language, title and the consolidation date are read from the file name, the folder and the first page; the report shows
what was guessed.  Entries get "if_absent": true -- a law the pack already has from the Bulletin Officiel is not added a second time
(use crosscheck_sgg to compare those).  Then: py -m legalrag.builder.from_law_pdf --batch batches/sgg.json [--install]"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .from_law_pdf import read_pages

_AR_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "ماي": 5, "مايو": 5, "يونيو": 6, "يوليو": 7, "يوليوز": 7, "غشت": 8, "أغسطس": 8,
              "اغسطس": 8, "شتنبر": 9, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نونبر": 11, "نوفمبر": 11, "دجنبر": 12, "ديسمبر": 12}
_FR_MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10,
              "novembre": 11, "décembre": 12, "decembre": 12}
_FOLDER_KIND = {"lois": "law", "decrets": "decree", "lois_organiques": "organic_law"}


def _iso(d: int, m: int, y: int) -> str | None:
    return f"{y:04d}-{m:02d}-{d:02d}" if 1 <= d <= 31 and 1 <= m <= 12 and 1990 <= y <= 2100 else None


def consolidated_date(text: str) -> str | None:
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"(?:du|au)\s+(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(?:بتاريخ|حتى|إلى غاية)\s+(\d{1,2})\s*([^\s\d]+)\s+(\d{4})", t)
    if m and m.group(2) in _AR_MONTHS:
        return _iso(int(m.group(1)), _AR_MONTHS[m.group(2)], int(m.group(3)))
    m = re.search(r"(?:موطدة|محينة)\s+بتاريخ\s+([^\s\d]+)\s+(\d{4})", t)  # month and year only: the 1st
    if m and m.group(1) in _AR_MONTHS:
        return _iso(1, _AR_MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"(\d{1,2})(?:er)?\s+([A-Za-zéûô]+)\s+(\d{4})", t)
    if m and m.group(2).lower() in _FR_MONTHS and re.search(r"consolid", t, re.I):
        return _iso(int(m.group(1)), _FR_MONTHS[m.group(2).lower()], int(m.group(3)))
    return None


def guess(path: Path) -> dict:
    stem = path.stem
    number = stem.replace("_", ".") if not re.match(r"^\d+_\d+$", stem) else stem.replace("_", ".")
    folder_kind = _FOLDER_KIND.get(path.parent.name.lower(), "law")
    kind = "dahir" if (folder_kind == "law" and stem.startswith("1_")) else folder_kind
    pages, _ = read_pages(path)
    first = "\n".join(pages[:2])
    ar = len(re.findall(r"[؀-ۿ]", first))
    lang = "ar" if ar > 0.3 * max(1, len(re.sub(r"\s", "", first))) else "fr"
    heads = [l.strip() for l in first.split("\n") if l.strip()]
    stop = re.compile(r"(Version consolid|صيغة|SECRÉTARIAT|الأمانة|Cette version|تم إعداد)", re.I)
    title_lines: list[str] = []
    for l in heads:
        if stop.search(l):
            break
        title_lines.append(l)
        if len(title_lines) >= 6:
            break
    title = re.sub(r"\s+", " ", " ".join(title_lines)).strip()[:240] or number
    cons = consolidated_date(first)
    e = {"file": str(path).replace("\\", "/"), "number": number, "kind": kind, "lang": lang, "consolidated_on": cons, "domain": "other",
         "source_kind": "sgg_consolidated", "if_absent": True, "min_articles": 1}
    e["title" if lang == "ar" else "title_fr"] = title
    if lang == "fr":
        e["title"] = None
    return e


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--out", default="batches/sgg.json")
    a = ap.parse_args(argv)
    entries = [guess(f) for f in sorted(Path(a.folder).rglob("*.md"))]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(entries, ensure_ascii=False, indent=1), "utf-8")
    nodate = [e["number"] for e in entries if not e["consolidated_on"]]
    print(f"{len(entries)} texts -> {a.out}   (ar {sum(e['lang']=='ar' for e in entries)}, fr {sum(e['lang']=='fr' for e in entries)})")
    print("no consolidation date found (will be refused until you add one):", ", ".join(nodate) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
