"""BO bridge: Bulletin Officiel PDFs / extracted markdown  ->  builder sources (the YAML/JSON `legalrag-build build` takes).

Steps (numbering follows the ingestion order):
 1. freeze_pdfs      copy every PDF unchanged into a read-only folder + manifest.json with sha256 (re-run verifies, never overwrites)
 2. (extraction)     done by your extract_bo_pdf.py; here we only REFUSE text with Arabic presentation forms (visual-order leak)
 3. structure        bo_structure.py (your chunk_bo.py parser): issue -> legal texts -> preamble / chapters / articles (المادة and الفصل, مكرر)
 4. provisions       one provision per article, one dated version (valid_from = effective date, valid_to open), source file + sha256,
                     trust level `single_source` (a BO text is one official source; a second official source upgrades it to `verified`)
 5. links            amends / repeals / implements edges read from the title of each text, resolved to instruments in the same run
 6. checks           the builder's own checks (numbering gaps, empty articles, overlapping versions ...) + the extra report below
 7. chunking         done by the builder (one article = one chunk, prefixed with title, path and validity dates)

Nothing here invents law: a text whose type, number or date cannot be read is listed in the report and left out, never guessed.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from ..text.arabic import presentation_form_count
from ..text.dates import extract_dates, to_iso
from . import bo_structure as bs

# ---- 1. freeze ------------------------------------------------------------------------------------------------------------------------


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def freeze_pdfs(src_dir: Path, frozen_dir: Path) -> dict:
    """Copy PDFs unchanged into `frozen_dir` (read-only) and record sha256. Safe to re-run: an existing frozen file is
    only verified; if it differs from the source, that is reported and NOTHING is overwritten."""
    frozen_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = frozen_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    report = {"copied": 0, "verified": 0, "changed_at_source": [], "frozen_modified": []}
    for pdf in sorted(src_dir.rglob("*.pdf")):
        rel = str(pdf.relative_to(src_dir))
        dest = frozen_dir / rel
        digest = _sha(pdf)
        if dest.exists():
            known = manifest.get(rel, {}).get("sha256")
            if _sha(dest) != (known or _sha(dest)):
                report["frozen_modified"].append(rel)  # the frozen copy no longer matches its recorded hash
            elif digest != _sha(dest):
                report["changed_at_source"].append(rel)  # the source file changed after freezing (kept as frozen)
            else:
                report["verified"] += 1
            manifest.setdefault(rel, {"sha256": _sha(dest), "bytes": dest.stat().st_size, "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, dest)
        dest.chmod(0o444)
        manifest[rel] = {"sha256": digest, "bytes": dest.stat().st_size, "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        report["copied"] += 1
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    return report


# ---- article numbers ---------------------------------------------------------------------------------------------------------------------

_UNITS = {"أول": 1, "اول": 1, "حاد": 1, "ثان": 2, "ثالث": 3, "رابع": 4, "خامس": 5, "سادس": 6, "سابع": 7, "ثامن": 8, "تاسع": 9, "عاشر": 10}
_TENS = {"عشر": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "أربعون": 40, "اربعون": 40, "أربعين": 40, "اربعين": 40, "خمسون": 50, "خمسين": 50}


def _ord_stem(w: str) -> str:
    w = re.sub(r"^(ال|و)+", "", w)
    return w if w in _TENS else re.sub(r"(ية|ي|ة|ى)$", "", w)


def parse_article_number(label: str) -> tuple[str | None, str]:
    """'المادة الأولى' -> ('1', ''); 'الفصل 12 مكررة' -> ('12 bis', ''); 'المادة 2.13' -> ('2.13', ''). None when unreadable."""
    rest = label.split(None, 1)[1] if len(label.split(None, 1)) > 1 else ""
    suffix = ""
    if re.search(r"مكرر[ةا]?\s*(مرتين|ثانيا)", rest):
        suffix = "ter"
    elif re.search(r"مكرر", rest):
        suffix = "bis"
    elif re.search(r"ثالثا", rest):
        suffix = "ter"
    rest = re.sub(r"\s*(مكرر[ةا]?\s*مرتين|مكرر[ةا]?|ثالثا|رابعا|خامسا)\s*", " ", rest).strip()
    m = re.fullmatch(r"(\d+)", rest)
    if m:
        return (m.group(1) + (f" {suffix}" if suffix else ""), suffix)
    if re.fullmatch(r"\d+(?:[.\-]\d+)+", rest):
        return (rest + (f" {suffix}" if suffix else ""), suffix)
    words = [w for w in re.split(r"\s+", rest) if w]
    total, seen = 0, False
    for w in words:
        s = _ord_stem(w)
        if s in _TENS:
            total += _TENS[s]; seen = True
        elif s in _UNITS:
            total += _UNITS[s]; seen = True
        elif s.replace("ال", "") in ("", "و"):
            continue
        else:
            return None, suffix
    # "الحادية عشرة" = 11: unit + 10 handled by summation (حادية=1 + عشرة=10)
    return ((str(total) + (f" {suffix}" if suffix else "")) if seen and total else None), suffix


# ---- instrument metadata -------------------------------------------------------------------------------------------------------------------

KIND_BY_TYPE = [  # (BO type word, instrument kind, id code)
    ("قانون تنظيمي", "organic_law", "ORG"),
    ("ظهير شريف", "dahir_law", "DAHIR"),
    ("ظهير", "dahir_law", "DAHIR"),
    ("مرسوم بقانون", "decree", "DECLAW"),
    ("مرسوم", "decree", "DECREE"),
    ("قانون إطار", "law", "LAW"),
    ("قانون", "law", "LAW"),
    ("قرار", "order", "ORDER"),
    ("مقرر", "order", "ORDER"),
    ("دورية", "circular", "CIRC"),
    ("منشور", "circular", "CIRC"),
    ("اتفاقية", "treaty", "TREATY"),
    ("اتفاق", "treaty", "TREATY"),
]
EDGE_PATTERNS = [  # on the subject line of a text: (regex, edge type)
    (re.compile(r"ب(?:تغيير|تتميم|تعديل|مراجعة)"), "amends"),
    (re.compile(r"ب(?:نسخ|إلغاء|الغاء)"), "repeals"),
    (re.compile(r"(?:لتطبيق|بتطبيق|المتخذ لتطبيق|المتعلق بتطبيق)"), "implements"),
]
_REF_TITLE = re.compile(r"(الظهير الشريف|المرسوم(?: بقانون| التطبيقي)?|القرار(?: المشترك)?|القانون(?: التنظيمي| الإطار)?|المقرر|الدورية)\s+رقم\s+(\d+(?:[.\-/]\d+)*)")


def _code_for(doc_type: str | None) -> tuple[str, str] | None:
    for word, kind, code in KIND_BY_TYPE:
        if doc_type and doc_type.startswith(word):
            return kind, code
    return None


def _ref_code(word: str) -> str:
    for w, _k, code in KIND_BY_TYPE:
        if word.startswith(w.split()[0]) or (w in word):
            return code
    return "LAW"


def _greg_date(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"فاتح\b", "1", text)  # "فاتح فبراير 2021" = 1 February 2021 (the date reader does not know the word)
    ds = [d for d in extract_dates(text) if d.precision == "day" and d.date.year >= 1900]
    return to_iso(ds[-1].date) if ds else None


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", s).strip("-")


# ---- 3-5. one BO markdown file -> sources ---------------------------------------------------------------------------------------------------


def parse_issue(md_path: Path) -> dict:
    text = md_path.read_text("utf-8")
    issue = bs.issue_meta(text, md_path.name)
    els, notes = bs.parse_md(text)
    els = bs.drop_furniture(els)
    els, toc_pages = bs.drop_toc(els, notes, False)
    els = bs.merge_headings(els)
    units = bs.split_units(els, issue)
    return {"issue": issue, "units": units, "notes": notes, "text": text}


def bo_to_sources(md_files: list[Path], pdf_root: Path | None = None, frozen_root: Path | None = None, md_root: Path | None = None) -> tuple[dict, dict]:
    """-> (sources dict for build_pack, report). `frozen_root` (from freeze_pdfs) supplies the PDF path + declared sha256 per issue."""
    manifest = {}
    if frozen_root and (frozen_root / "manifest.json").exists():
        manifest = json.loads((frozen_root / "manifest.json").read_text("utf-8"))
    src: dict = {"sources": [], "instruments": [], "provisions": [], "edges": []}
    rep: dict = {"issues": 0, "texts_seen": 0, "instruments": 0, "articles": 0, "skipped": [], "warnings": [], "unresolved_edges": []}
    seen_ids: dict[str, int] = {}
    pending_edges: list[tuple[str, str, str, str]] = []  # (from_instr, etype, ref_code, ref_number)
    index: dict[tuple[str, str], str] = {}  # (code, number) -> instrument_id

    for md in md_files:
        data = parse_issue(md)
        inum = str(data["issue"]["number"]).replace(" ", "")
        rep["issues"] += 1
        if presentation_form_count(data["text"]) > 0:
            rep["skipped"].append({"file": md.name, "reason": "broken_arabic_order: presentation forms found; re-extract (extract_bo_pdf.py) before ingesting"})
            continue
        # source (the PDF) ------------------------------------------------------------------------------------------------------------
        rel = None
        if frozen_root and md_root:
            try:
                r = str(md.relative_to(md_root).with_suffix(".pdf"))
                rel = r if r in manifest else None
            except ValueError:
                rel = None
        if frozen_root and rel is None:
            rep["warnings"].append({"where": md.name, "code": "pdf_not_frozen", "detail": "no frozen PDF with this name: provenance hash missing"})
        skey = f"BO_{inum}"
        sdef = {"key": skey, "kind": "bo_pdf", "edition": "official", "label": f"Bulletin Officiel n° {inum}", "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if rel:
            sdef["path"] = str(frozen_root / rel)
            sdef["url"] = (frozen_root / rel).resolve().as_uri()  # where the page images come from later
            sdef["sha256"] = manifest[rel]["sha256"]
        src["sources"].append(sdef)
        issue_greg = _greg_date(data["issue"].get("date_gregorian"))

        for ui, u in enumerate(data["units"]):
            rep["texts_seen"] += 1
            title = u["title"]
            if not title:
                rep["skipped"].append({"file": md.name, "unit": ui, "reason": "no title (announcement / cover block)"})
                continue
            tinfo = bs.parse_title(title)
            kc = _code_for(tinfo["doc_type"])
            if not kc:
                rep["skipped"].append({"file": md.name, "unit": ui, "title": title[:80], "reason": f"type not a legal text: {tinfo['doc_type']}"})
                continue
            kind, code = kc
            if not tinfo["doc_number"]:
                rep["skipped"].append({"file": md.name, "unit": ui, "title": title[:80], "reason": "number not readable in title"})
                continue
            bo_date = issue_greg
            doc_date = _greg_date(tinfo["doc_date_gregorian"]) or _greg_date(title)
            effective = bo_date or doc_date
            if not effective:
                rep["skipped"].append({"file": md.name, "unit": ui, "title": title[:80], "reason": "no readable date: cannot date the versions"})
                continue
            iid = f"{code}_{_slug(tinfo['doc_number'])}"
            if iid in seen_ids:  # same type+number seen twice (corrigendum / republication): keep both, distinguish by issue
                iid = f"{iid}_BO{inum}"
            seen_ids[iid] = 1
            parts = bs.split_parts(u)
            arts = [p for p in parts if p["kind"] == "article"]
            if not arts:
                rep["skipped"].append({"file": md.name, "unit": ui, "title": title[:80], "reason": "no articles (single-paragraph text, announcement or table-only)"})
                continue
            index[(code, tinfo["doc_number"])] = iid
            src["instruments"].append({
                "instrument_id": iid, "kind": kind, "number": tinfo["doc_number"], "title_ar": title[:500], "bo_number": inum, "bo_date": bo_date,
                "promulgation_date": doc_date, "effective_date": effective, "domain": "other",
                "language_availability": {"ar": "official"}, "status_note": "effective_date assumed = BO publication date; check the text for a later entry-into-force",
            })
            rep["instruments"] += 1
            rep["warnings"].append({"where": iid, "code": "effective_date_assumed", "detail": f"valid_from = {effective} (BO date); review if the text sets another date"})
            subject = tinfo["subject"] or ""
            for rx, etype in EDGE_PATTERNS:
                if rx.search(subject):
                    for m in _REF_TITLE.finditer(subject):
                        pending_edges.append((iid, etype, _ref_code(m.group(1)), m.group(2)))
                    break
            used: set[str] = set()
            for p in arts:
                num, suffix = parse_article_number(p["label"])
                if not num:
                    rep["warnings"].append({"where": iid, "code": "article_number_unreadable", "detail": p["label"]})
                    continue
                if num in used:
                    rep["warnings"].append({"where": iid, "code": "duplicate_article", "detail": f"{num}: later occurrence ignored (quoted amendment?)"})
                    continue
                used.add(num)
                body = "\n".join(p["lines"]).strip()
                prov = {
                    "instrument_id": iid, "number": num, "path": p.get("chapter") or None, "page": p.get("page"), "page_end": p.get("page_end") or p.get("page"),
                    "versions": [{"valid_from": effective, "valid_to": None, "source": skey, "controlling_lang": "ar", "texts": {"ar": {"text": body, "edition": "official"}}}],
                }
                if not num.split()[0].isdigit():  # dotted numbers (2.13): explicit id, ordinal 0
                    prov["provision_id"] = f"{iid}_ART_{_slug(num)}"
                src["provisions"].append(prov)
                rep["articles"] += 1

    for fid, etype, code, number in pending_edges:
        tid = index.get((code, number))
        if tid and tid != fid:
            src["edges"].append({"from_kind": "instrument", "from": fid, "to_kind": "instrument", "to": tid, "type": etype, "source": "regex", "confidence": 0.9})
        else:
            rep["unresolved_edges"].append({"from": fid, "type": etype, "target": f"{code} {number}", "note": "target text not in this run (may be in the base registry)"})
    return src, rep
