"""Add the Bulletin Officiel des Collectivités Territoriales (الجريدة الرسمية للجماعات الترابية) -- local council decisions -- as their own texts.

    py -m legalrag.builder.from_boct data/boct                 (report only)
    py -m legalrag.builder.from_boct data/boct --install

These issues are not laws with numbered articles: they are many separate decisions (delegations, tax rates, trade lists, regulations of
communes, provinces, regions).  Each issue becomes ONE instrument (id MA_BOCT_<issue>, short code "BOCT <issue>", kind administrative_guidance) and its
text is cut into passages of about 1,500 characters at paragraph boundaries, in page order; passage N carries the page(s) it came from and the section
headings above it.  So an answer cites "الجريدة الرسمية للجماعات الترابية عدد 62، المقطع 40 (ص. 31)" and not an article.  Issues already in the pack
are skipped.  Embedding ~50 issues takes a long time on CPU (tens of thousands of passages): run it overnight, or install a few at a time with --only."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .from_bo import parse_article_number
from .from_law_pdf import normalise_text

_PAGE = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)
_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "ماي": 5, "مايو": 5, "يونيو": 6, "يوليو": 7, "يوليوز": 7, "غشت": 8, "أغسطس": 8, "اغسطس": 8,
           "شتنبر": 9, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نونبر": 11, "نوفمبر": 11, "دجنبر": 12, "ديسمبر": 12}
_MONTH_FIX = {"فرباير": "فبراير", "نونرب": "نونبر", "ماي": "ماي", "مايي": "ماي", "يوليوز": "يوليوز", "يوليو": "يوليو", "دجنرب": "دجنبر"}
_HEADER = re.compile(r"(الجريدة الرسمية للجماعات الترابية|^العدد\s)")
TARGET = 1500


def _nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def issue_info(text: str, filename: str) -> tuple[str | None, str | None]:
    """-> (issue number, ISO date) from the running header "العدد الثاني و الستون 15 شعبان 1446 (14 فبراير 2025)"."""
    flat = re.sub(r"[ \t]+", " ", text[:60000])
    num = date = None
    m = re.search(r"العدد\s+(.{3,40}?)\s+\d{0,2}\s*[^\s\d]+\s*\d{4}\s*\(", flat.replace("\n", " "))
    if m:
        words = re.sub(r"\s+", " ", m.group(1).replace(" و ", " و")).strip()
        for cand in (words, words.replace(" ", "")):
            n, _ = parse_article_number(f"المادة {cand}")
            if n and str(n).isdigit() and 1 <= int(n) <= 400:
                num = str(int(n))
                break
    import collections

    fr = {"janvier": 1, "jan": 1, "fevrier": 2, "fevier": 2, "fev": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "oct": 10,
          "novembre": 11, "nov": 11, "decembre": 12, "dec": 12}
    # the running header repeats on every page: "<hijri day month 14xx> (<day month year>)", so the most frequent date after a hijri year is the issue date
    def _votes(lines):
        v = collections.Counter()
        for l in lines:
            l = re.sub(r"\s+", " ", l.replace("|", " "))
            for dm in re.finditer(r"1[34]\d\d\s*\(?\s*(\d{1,2}|فاتح)\s+([^\d()]{2,14}?)\s*(\d{4})\s*\)", l):
                mon = _MONTH_FIX.get(dm.group(2).replace(" ", ""), dm.group(2).replace(" ", ""))
                if mon in _MONTHS:
                    day = 1 if dm.group(1) == "فاتح" else int(dm.group(1))
                    v[f"{int(dm.group(3)):04d}-{_MONTHS[mon]:02d}-{day:02d}"] += 1
        return v

    # tier 1: the cover (first lines) -- the running header of a few issues was copied from the previous issue, the cover is right;
    # tier 2: header lines repeated on every page; tier 3: any short line with "<hijri> (<gregorian>)"
    short = [l for l in text.split("\n") if len(l) < 170]
    tiers = [(text.split("\n")[:60], 1),
             ([l for l in short if re.search(r"الجريدة الرسمية للجماعات|العدد|الجماعات الترابية|الجماعات المحلية", l)], 5),
             (short, 5)]
    for lines, need in tiers:
        v = _votes(lines)
        if v and v.most_common(1)[0][1] >= need:
            date = v.most_common(1)[0][0]
            break
    if not date:
        for fm in re.finditer(r"(?<!\d)(\d{1,2})\s+([A-Za-zéû]+)\s+(\d{4})", filename):  # fall back on the file name
            if fm.group(2).lower() in fr and 1 <= int(fm.group(1)) <= 31:
                date = f"{int(fm.group(3)):04d}-{fr[fm.group(2).lower()]:02d}-{int(fm.group(1)):02d}"
                break
    if not num:
        fm = re.search(r"(?:BOCT|BOCL|BLOC2?|bo|boct|الرسمية|rasmiya)[^\d]{0,12}(\d{2,3})", filename, re.I) or re.search(r"(\d{2,3})", filename)
        num = str(int(fm.group(1))) if fm else None
    return num, date


def passages(md: Path) -> tuple[list[dict], dict]:
    text = md.read_text("utf-8")
    parts = _PAGE.split(text)
    out: list[dict] = []
    heads: list[str] = []
    buf: list[str] = []
    buf_pages: list[int] = []
    size = 0
    skipped = 0

    def flush():
        nonlocal buf, buf_pages, size
        body = "\n".join(buf).strip()
        if len(body) >= 60:
            out.append({"text": body, "page": min(buf_pages), "page_end": max(buf_pages), "path": " / ".join(heads[-2:]) or None})
        buf, buf_pages, size = [], [], 0

    for i in range(1, len(parts) - 1, 2):
        pno, t = int(parts[i]), parts[i + 1]
        t = re.sub(r"^>\s*\*\*NOTE:\*\*.*$", "", t, flags=re.M)
        t = re.sub(r"^-{3,}\s*$", "", t, flags=re.M)
        if re.search(r"الفهرس", t[:400]) and pno < 12:  # the table of contents repeats every decision's title: skip it
            skipped += 1
            continue
        for raw in t.split("\n"):
            ln = raw.strip()
            if not ln or re.fullmatch(r"[\d\s.\-]+", ln) or re.fullmatch(r"[|:\- ]+", ln):
                continue
            if _HEADER.search(ln) and len(ln) < 140:
                continue
            ishead = ln.startswith("#")
            ln = normalise_text(re.sub(r"^#{1,6}\s*", "", ln))
            if not ln:
                continue
            if ishead and len(ln) < 120:
                if size >= TARGET // 3:
                    flush()
                heads.append(ln)
                continue
            if size + len(ln) > TARGET and size >= TARGET // 2:
                flush()
            buf.append(ln)
            buf_pages.append(pno)
            size += len(ln)
    flush()
    return out, {"pages": (len(parts) - 1) // 2, "toc_pages_skipped": skipped, "passages": len(out)}


def to_sources(md: Path) -> tuple[dict | None, dict]:
    ps, rep = passages(md)
    text = md.read_text("utf-8")
    num, date = issue_info(text, md.name)
    try:
        import json as _j
        ov = _j.loads((md.parent / "dates.json").read_text("utf-8"))
        if num in ov:
            date = ov[num]
    except Exception:  # noqa: BLE001
        pass
    rep.update({"file": md.name, "issue": num, "date": date})
    rep["problems"] = []
    if not num:
        rep["problems"].append("issue number not found")
    dated = bool(date)
    if not date:
        date = "2000-01-01"  # placeholder, flagged below
    rep["date_guessed"] = not dated
    if len(ps) < 5:
        rep["problems"].append(f"only {len(ps)} passages: the file has no text layer (needs OCR)")
    if rep["problems"]:
        return None, rep
    iid = f"MA_BOCT_{num}"
    skey = f"BOCT_{num}"
    sha = hashlib.sha256(md.read_bytes()).hexdigest()
    title = f"الجريدة الرسمية للجماعات الترابية عدد {num}"
    src = {
        "sources": [{"key": skey, "kind": "other", "edition": "official", "label": f"{title} ({md.name})", "sha256": sha,
                     "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}],
        "instruments": [{"instrument_id": iid, "kind": "administrative_guidance", "number": f"BOCT-{num}", "short_code": f"BOCT {num}", "title_ar": title,
                         "title_fr": f"Bulletin officiel des collectivités territoriales n° {num}", "bo_number": num, "bo_date": date, "promulgation_date": date,
                         "effective_date": date, "domain": "other", "language_availability": {"ar": "official"}, "consolidated_text_available": False,
                         "status_note": "local council decisions published in the BOCT; passages in page order, not numbered articles" + ("; ISSUE DATE NOT FOUND, 2000-01-01 is a placeholder: set the real date" if rep["date_guessed"] else "")}],
        "provisions": [{"instrument_id": iid, "number": str(k), "path": p["path"], "page": p["page"], "page_end": p["page_end"],
                        "versions": [{"valid_from": date, "valid_to": None, "source": skey, "controlling_lang": "ar",
                                      "texts": {"ar": {"text": p["text"], "edition": "official"}}}]} for k, p in enumerate(ps, start=1)],
        "edges": [],
    }
    rep["instrument_id"] = iid
    return src, rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--only", nargs="+", help="issue numbers, comma- or space-separated, e.g. 62,63 or 62 63")
    a = ap.parse_args(argv)
    only = {x.strip() for chunk in a.only for x in chunk.split(",") if x.strip()} if a.only else None
    ctx = None
    if a.install:
        from ..config import Settings
        from ..state import build_context
        from .from_law_pdf import install

        s = Settings()
        ctx = build_context(s)
        if not ctx.pack_usable():
            print("no usable law pack:", ctx.pack_error)
            return 2
    summary = []
    seen: set[str] = set()
    for f in sorted(Path(a.folder).rglob("*.md")):
        if f.name.upper().startswith("BO_"):  # an ordinary Bulletin Officiel page, not a BOCT issue: the BO updater handles those
            print("  skipped (not a BOCT issue):", f.name)
            continue
        src, rep = to_sources(f)
        label = f"{f.name[:44]:44} issue={rep.get('issue')} date={rep.get('date')}{'(?)' if rep.get('date_guessed') else ''} pages={rep.get('pages')} passages={rep.get('passages')}"
        if src is None:
            summary.append((label, "NOT ADDED: " + rep["problems"][0]))
            continue
        iid = src["instruments"][0]["instrument_id"]
        if iid in seen:
            summary.append((label, f"SKIPPED: issue {rep['issue']} appears twice in the folder"))
            continue
        seen.add(iid)
        if only and rep["issue"] not in only:
            continue
        if ctx is not None:
            if iid in ctx.pack.instrument_ids():
                summary.append((label, "SKIPPED: already in the pack"))
                continue
            try:
                install(src, ctx)
                from ..state import build_context as _b
                ctx = _b(ctx.settings)
                summary.append((label, "ADDED"))
            except Exception as ex:  # noqa: BLE001
                summary.append((label, f"NOT ADDED: {ex}"))
        else:
            summary.append((label, "ok (report only)"))
    print("SUMMARY")
    for l, r in summary:
        print(" ", l, "->", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
