"""Law PDF importer: ONE law or code in a PDF (consolidated text from the SGG site, Adala, a book scan with a text layer...)  ->  builder sources.

For laws that are not (or not only) in the Bulletin Officiel issues the update button reads: the Constitution, the Family Code, the Labour Code,
the Dahir of Obligations and Contracts, the Penal Code ...  The output is the same `sources` dict as `from_bo.bo_to_sources`, so the existing
append / checks / install code puts it into the pack.

    python -m legalrag.builder.from_law_pdf FILE.pdf --number 65.99 --title "مدونة الشغل" --effective 2004-06-08 --domain labor            # report only
    python -m legalrag.builder.from_law_pdf FILE.pdf --number 65.99 --title "مدونة الشغل" --effective 2004-06-08 --domain labor --install  # add to the pack

Steps: 1 read the text page by page (and repair Arabic that came out in visual order / presentation forms)   2 drop page furniture (repeated
headers, footers, page numbers)   3 find the article headings (المادة / الفصل / Article, ordinals included) and check they count up   4 follow the
chapter headings (الكتاب / الباب / القسم / الفرع) as the path   5 one provision per article, one dated version, page numbers kept for the PDF viewer
6 a REPORT: how many articles, which numbers are missing, which headings were refused, the first and last article.  Nothing is guessed: a heading
that does not fit the numbering is treated as text of the previous article and listed.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .from_bo import parse_article_number

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # marks and tatweel
_AR = re.compile(r"[؀-ۿ]")

KINDS = {  # --kind -> (instrument kind, id code)
    "law": ("law", "LAW"), "organic_law": ("organic_law", "ORG"), "dahir": ("dahir_law", "DAHIR"), "decree": ("decree", "DECREE"),
    "constitution": ("constitution", "CONST"), "code": ("law", "LAW"),
}
DOMAINS = ["civil_procedure", "commercial", "criminal", "family", "labor", "legal_profession", "obligations", "property", "tax", "traffic", "other"]

_ART_KW = {"ar": ("المادة", "الفصل"), "fr": ("Article", "Art.", "Art")}
_CHAPTER_LEVEL = {  # first word of a structural heading -> depth
    "الكتاب": 1, "الجزء": 1, "العنوان": 1, "الباب": 2, "القسم": 2, "الفرع": 3, "الفصل": 3, "المبحث": 3,
    "livre": 1, "partie": 1, "titre": 2, "chapitre": 3, "section": 4, "sous-section": 5,
}
_SUFFIX_WORDS = {"مكرر", "مكررة", "المكرر", "المكررة", "مرتين", "ثلاث", "مرات", "ثانيا", "ثالثا", "رابعا", "خامسا", "bis", "ter", "quater"}


# =================================================================================================================== 1. read
def normalise_text(text: str) -> str:
    """Presentation forms -> base letters (NFKC), digits -> 0-9, marks and tatweel out, spaces tidy."""
    t = unicodedata.normalize("NFKC", text or "").translate(_AR_DIGITS)
    t = _TASHKEEL.sub("", t)
    t = fix_lam_alef(t)
    return t.replace("‏", "").replace("‎", "").replace("‫", "").replace("‬", "").replace(" ", " ")


_BROKEN_AL = re.compile(r"(?<![\u0621-\u064A])([وفبك]?)ا([أإآا])ل")


def fix_lam_alef(t: str) -> str:
    """Some PDFs (Adala) store the lam-alef ligature as alef + lam: "الأولى" comes out "األولى", "الإمضاء" "اإلمضاء", "لله" "هلل".
    Only the safe, word-initial cases are repaired (no Arabic word starts with "األ" / "اإل" / "اآل" / "اال"), and only when the text
    clearly has the defect, so correct texts are never touched."""
    if not _BROKEN_AL.search(t):
        return t
    t = _BROKEN_AL.sub(lambda m: m.group(1) + "ال" + m.group(2), t)
    return re.sub(r"(?<![\u0621-\u064A])هلل(?![\u0621-\u064A])", "لله", t)


def looks_reversed(text: str) -> bool:
    """Visual-order extraction writes Arabic backwards: the common words appear reversed ("ةداملا")."""
    fwd = len(re.findall(r"المادة|الفصل|القانون|الباب|مكرر", text))
    rev = len(re.findall(r"ةداملا|لصفلا|نوناقلا|بابلا|ررکم|ررمك", text))
    return rev > fwd and rev >= 3


def fix_visual_order(text: str) -> str:
    """Reverse every line character by character, then put digit runs back (they were reversed too)."""
    out = []
    for line in text.split("\n"):
        r = line[::-1]
        r = re.sub(r"\d+(?:[.\-/]\d+)*", lambda m: m.group(0)[::-1], r)
        out.append(r)
    return "\n".join(out)


_PAGE_MARK = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.I)


def read_md_pages(md: Path) -> tuple[list[str], dict]:
    """The markdown that extract_bo_pdf.py / extract_law_pdf.py wrote: pages are cut at `<!-- page N -->`; headings lose their `#`, notes and footnote marks go."""
    text = md.read_text("utf-8")
    parts = _PAGE_MARK.split(text)  # [before, "1", text1, "2", text2 ...]
    pages: list[str] = []
    low: list[int] = []
    for i in range(1, len(parts) - 1, 2):
        t = parts[i + 1]
        if re.search(r"LOW COVERAGE", t):
            low.append(int(parts[i]))
        t = re.sub(r"^>\s*\*\*NOTE:\*\*.*$", "", t, flags=re.M)
        t = re.sub(r"^-{3,}\s*$", "", t, flags=re.M)
        t = re.sub(r"^#{1,6}\s*", "", t, flags=re.M)
        t = re.sub(r"\[\^\d+\]", "", t)
        # French SGG texts: "... fin de phrase. Article 2" -> the heading goes on its own line
        t = re.sub(r"(?<=\S)[ \t]+((?:Article|ARTICLE)\s+(?:\d+|[Pp]remier|PREMIER)(?:\s+(?:bis|ter|quater))?)[ \t]*$", r"\n\1", t, flags=re.M)
        t = re.sub(r"^\s*-?\s*\d{1,4}\s*-?\s*$", "", t, flags=re.M)  # "310 -", "- 6 -": page numbers
        pages.append(normalise_text(t))
    return pages, {"pages": len(pages), "scanned_pages": [], "low_coverage_pages": low, "reversed": False, "from_markdown": True}


def read_pages(pdf: Path) -> tuple[list[str], dict]:
    """-> (text of each page, info).  pdfplumber first; when it returns nothing for a page the page is reported as scanned (no OCR here)."""
    if pdf.suffix.lower() == ".md":
        return read_md_pages(pdf)
    import pdfplumber

    logging.getLogger("pdfminer").setLevel(logging.ERROR)  # "Could not get FontBBox" noise
    pages: list[str] = []
    scanned: list[int] = []
    with pdfplumber.open(pdf) as d:
        for i, pg in enumerate(d.pages, start=1):
            t = pg.extract_text() or ""
            if len(t.strip()) < 15:
                scanned.append(i)
            pages.append(t)
    joined = "\n".join(pages)
    info = {"pages": len(pages), "scanned_pages": scanned, "reversed": False}
    if looks_reversed(normalise_text(joined)):
        info["reversed"] = True
        pages = [normalise_text(fix_visual_order(p)) for p in pages]  # reverse FIRST: a lam-alef ligature is one character that NFKC splits in two
    else:
        pages = [normalise_text(p) for p in pages]
    return pages, info


# =================================================================================================================== 2. clean
def clean_pages(pages: list[str]) -> tuple[list[list[str]], dict]:
    """Lines per page without page furniture: lines that repeat on many pages (running header / footer), bare page numbers."""
    lines = [[re.sub(r"\s+", " ", ln).strip() for ln in p.split("\n")] for p in pages]
    lines = [[ln for ln in pg if ln] for pg in lines]
    key = lambda ln: re.sub(r"\d+", "#", ln)  # noqa: E731
    seen: dict[str, int] = {}
    for pg in lines:
        for k in {key(ln) for ln in pg}:
            seen[k] = seen.get(k, 0) + 1
    n = len(pages)
    repeated = {k for k, c in seen.items() if n >= 2 and c >= max(2, int(0.4 * n + 0.5)) and len(k) < 120
                and not re.match(r"^(المادة|الفصل|الباب|القسم|الكتاب|الفرع|Article|Art|Titre|Chapitre|Livre|Section)\b", k)}
    out: list[list[str]] = []
    dropped = 0
    for pg in lines:
        keep = []
        for ln in pg:
            if re.fullmatch(r"[-–— ]*\d{1,4}[-–— ]*", ln) or key(ln) in repeated:
                dropped += 1
                continue
            keep.append(ln)
        out.append(keep)
    return out, {"furniture_lines_dropped": dropped}


# =================================================================================================================== 3-4. structure
@dataclass
class Article:
    number: str
    label: str
    path: str | None
    page: int
    page_end: int
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.lines).strip()


_RANGE = re.compile(r"^(?:الفصول|المواد)\s+(?:من\s+)?(\d+)\s*(?:[-–—]|إلى|الى|و)\s*(\d+)\s*[.:]?\s*$")


def _num_token(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)*|\d{1,2}-\d{1,2}", tok))


def parse_heading(line: str, lang: str = "ar") -> tuple[str, str, str] | None:
    """A line that starts an article -> (number, label, rest of the line after the number); None if it does not.
    "المادة 5 - يجب" -> ("5", "المادة 5", "يجب");  "الفصل الأول" -> ("1", ...);  "المادة 12 مكررة مرتين." ;  "Article 7 bis"."""
    m = re.match(r"^(المادة|الفصل)(?:\s+|(?=\d))(.+)$", line) if lang == "ar" else re.match(r"^(Article|Art\.?)\s+(.+)$", line, re.I)
    if not m:
        return None
    kw, rest = m.group(1), m.group(2)
    if lang != "ar":
        rest = re.sub(r"^(?:premier|1er|1ER)\b", "1", rest, flags=re.I)
    rev = re.match(r"^(\d{1,2})-(\d{2,3})(?=\D|$)", rest) if lang == "ar" else None
    if rev and int(rev.group(1)) < int(rev.group(2)):  # the PDF text order flips "256-1" into "1-256"
        rest = f"{rev.group(2)}-{rev.group(1)}" + rest[rev.end():]
    toks = rest.split(" ")
    best: tuple[str, str, int] | None = None
    # digits: "5", "2.13", then optional suffix words
    if toks and _num_token(toks[0].rstrip(".:-–—")):
        n = 1
        word = toks[0].rstrip(".:-–—")
        while n < len(toks) and toks[n].strip(".:-–—،,").lower() in _SUFFIX_WORDS:
            n += 1
        label = f"{kw} {word}" + ("".join(" " + t.strip(".:-–—،,") for t in toks[1:n]))
        num, _sfx = parse_article_number(label) if lang == "ar" else _fr_number(word, toks[1:n])
        if num:
            best = (num, label, n)
    elif lang == "ar":  # ordinals: the longest run of words that reads as a number ("الحادية عشرة", "الثانية والعشرون مكررة")
        for n in range(min(5, len(toks)), 0, -1):
            part = " ".join(t.strip(".:-–—،,") for t in toks[:n])
            num, _sfx = parse_article_number(f"{kw} {part}")
            if num and all(t.strip(".:-–—،,") for t in toks[:n]):
                best = (num, f"{kw} {part}", n)
                break
    if not best:
        return None
    num, label, n = best
    tail = " ".join(toks[n:]).lstrip(".:-–— ").strip()
    return num, label, tail


def _fr_number(word: str, sfx: list[str]) -> tuple[str | None, str]:
    s = next((t.lower().strip(".,") for t in sfx if t.lower().strip(".,") in {"bis", "ter", "quater"}), "")
    return (word + (f" {s}" if s else ""), s)


def _base(num: str) -> int | None:
    m = re.match(r"\d+", num)
    return int(m.group()) if m else None


def _structural(line: str) -> tuple[int, str] | None:
    """A chapter heading: a structural word followed by a number or an ordinal ("الباب الثاني", "Titre III", "القسم 2")."""
    parts = line.split(" ", 2)
    first = parts[0].lower().rstrip(":")
    if first not in _CHAPTER_LEVEL or len(parts) < 2:
        return None
    second = parts[1].strip(".:-–—،,")
    ok = bool(re.fullmatch(r"\d+|[IVXivx]+|premier|première|unique", second)) or (parse_article_number(f"المادة {second}")[0] is not None)
    return (_CHAPTER_LEVEL[first], line) if ok else None


def _unglue(ln: str, last: int) -> str:
    """A footnote call number stuck to a heading: «المادة 331 5» / «المادة 3337» / «المادة 45338» -> the number that follows the sequence («المادة 5», «3», «45»)."""
    m = re.match(r"^(المادة|الفصل)\s+(\d(?:[\d ]*\d)?)(.*)$", ln)
    if not m or last <= 0:
        return ln
    m2 = re.match(r"^(المادة|الفصل)\s+(\d+)([\d\- ]*)$", ln)
    if m2 and m2.group(3).strip() and not m2.group(2) == str(last + 1):
        g = m2.group(2) + m2.group(3).replace(" ", "")
        nxt = str(last + 1)
        if g.startswith(nxt) and len(g) > len(nxt) and re.fullmatch(r"[\d\-]+", g[len(nxt):]):
            return f"{m2.group(1)} {nxt}"
    digits = m.group(2).replace(" ", "")
    if len(digits) <= 3 and " " not in m.group(2):
        return ln
    for i in range(1, len(digits)):
        a, b = digits[:i], digits[i:]
        for art, fn in ((a, b), (b, a)):
            if art and not art.startswith("0") and int(art) == last + 1 and len(fn) <= 3:
                return f"{m.group(1)} {art}{m.group(3)}"
    return ln


def split_articles(pages_lines: list[list[str]], lang: str = "ar", max_gap: int = 5, force_word: str | None = None) -> tuple[list[Article], dict]:
    """The core: page lines -> articles with their chapter path.  A heading is accepted only when its number follows the sequence."""
    # which word carries the articles?  (المادة in modern laws, الفصل in the older codes) -- the one with more line-start headings
    cnt: dict[str, int] = {}
    for pg in pages_lines:
        for ln in pg:
            h = parse_heading(ln, lang)
            if h:
                w = h[1].split(" ", 1)[0] if lang == "ar" else "Article"
                cnt[w] = cnt.get(w, 0) + 1
    art_word = force_word or (max(cnt, key=lambda k: cnt[k]) if cnt else None)  # force_word: a book that holds two codes (الفصل and المادة)
    rep: dict = {"toc_discarded": 0, "article_word": art_word, "refused_headings": [], "duplicates": [], "gaps": [], "preamble_lines": 0}
    arts: list[Article] = []
    by_num: dict[str, Article] = {}
    cur: Article | None = None
    last = 0
    levels: dict[int, str] = {}

    def path_now() -> str | None:
        return " / ".join(levels[k] for k in sorted(levels)) or None

    for pno, pg in enumerate(pages_lines, start=1):
        for ln in pg:
            rg = _RANGE.match(ln) if lang == "ar" else None
            if rg and int(rg.group(1)) <= last + 1 <= int(rg.group(2)) + 1 and int(rg.group(2)) - int(rg.group(1)) < 300:  # also at the start: a code whose first articles were repealed
                last = max(last, int(rg.group(2)))  # "الفصول 19 - 23" : repealed / reserved numbers, no text
                continue
            if lang == "ar":
                ln = _unglue(ln, last)
            h = parse_heading(ln, lang)
            if h and lang == "ar" and h[1].split(" ", 1)[0] != art_word:
                h = None  # the other word is a chapter heading in this text (الفصل الأول: ... in a law whose articles are المادة)
            if h:
                num, label, tail = h
                b = _base(num)
                ok = False
                if b is not None and b <= 1 and len(arts) >= 2 and last >= 3 and (sum(len(a.body) for a in arts) < 40 * len(arts) or last <= 12):
                    # numbering starts over and everything so far was bare headings: that was the table of contents, the text starts here
                    rep["toc_discarded"] = len(arts)
                    arts.clear()
                    by_num.clear()
                    levels = {}
                    cur, last = None, 0
                if b is not None:
                    if not arts:
                        ok = b <= 3 or (last > 0 and b == last + 1)  # a range of repealed articles before it ("المواد من 1 إلى 37") sets where it starts;  the first article (some texts start at 0/1/2 or at 1 after a preamble); a stray 'المادة 5' in a preamble must not start the text
                    elif b == last + 1 or (b == last and num != (cur.number if cur else "")):
                        ok = True
                    elif last < b <= last + max_gap:  # a jump forward: only a line that reads as a heading, not a cross-reference ("المادة 52 أعلاه ...")
                        ok = len(ln) <= 110 and not re.search(r"أعلاه|أدناه|السالف|السابق|من القانون|من هذه|من هذا|وما يليها|وما بعدها|بعده", tail)
                else:
                    ok = bool(arts)  # dotted numbers (2.13): accepted inside a text that already started
                if ok:
                    if b is not None and b > last + 1 and arts:
                        rep["gaps"].append(f"{last + 1}..{b - 1}" if b - 1 > last + 1 else str(last + 1))
                    cur = Article(num, label, path_now(), pno, pno, [tail] if tail else [])
                    if num in by_num:  # a table of contents line, or a quoted amendment: keep the one with more text at the end
                        rep["duplicates"].append(num)
                    arts.append(cur)
                    by_num.setdefault(num, cur)
                    if b is not None:
                        last = max(last, b)
                    continue
                rep["refused_headings"].append({"page": pno, "line": ln[:80], "why": f"number {num} does not follow {last}"})
            st = _structural(ln)
            if st and (not cur or len(ln) < 90) and not (lang == "ar" and art_word == "الفصل" and ln.startswith("الفصل")):
                depth, text = st
                levels = {k: v for k, v in levels.items() if k < depth}
                levels[depth] = text[:140]
                continue
            if cur is not None:
                cur.lines.append(ln)
                cur.page_end = pno
            else:
                rep["preamble_lines"] += 1
    # duplicates: keep, per number, the occurrence with the longest text (a TOC line is short)
    best: dict[str, Article] = {}
    for a in arts:
        if a.number not in best or len(a.body) > len(best[a.number].body):
            best[a.number] = a
    out = [a for a in arts if best[a.number] is a]
    if out:  # the last article runs on into the index of the book: cut at the first index-looking line
        last_a = out[-1]
        for k, l in enumerate(last_a.lines):
            if k > 0 and (re.fullmatch(r"(?:ال)?فهرس", l.strip()) or re.fullmatch(r"\d{6,}", l.strip())):
                last_a.lines = last_a.lines[:k]
                break
    return out, rep


# =================================================================================================================== 5. sources
def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", s).strip("-")


def law_pdf_to_sources(pdf: Path, meta: dict, frozen_dir: Path | None = None) -> tuple[dict, dict]:
    """-> (sources, report).  `meta`: number, title_ar (or title_fr), kind, effective (YYYY-MM-DD), domain, lang, bo_number, bo_date, promulgation,
    short_code, source_kind, consolidated_on, min_articles."""
    lang = meta.get("lang", "ar")
    pages, info = read_pages(pdf)
    lines, furniture = clean_pages(pages)
    arts, rep = split_articles(lines, lang, force_word=meta.get("article_word"))
    rep.update(info)
    rep.update(furniture)
    kind, code = KINDS[meta.get("kind", "law")]
    number = str(meta["number"]).strip()
    iid = f"{code}_{_slug(number)}" + (f"_{_slug(str(meta['id_suffix']))}" if meta.get("id_suffix") else "")  # a new edition installed beside a retired one
    effective = meta.get("effective") or meta.get("promulgation") or meta.get("bo_date") or meta.get("consolidated_on")
    rep["problems"] = []
    if not effective:
        rep["problems"].append("a date is needed: --effective (entry into force), or --promulgation / --bo-date / --consolidated-on")
    min_articles = int(meta.get("min_articles", 3))
    if len(arts) < min_articles:
        rep["problems"].append(f"only {len(arts)} article(s) found (minimum {min_articles}): the PDF has no text layer, or its headings are not المادة/الفصل/Article {number}")
    if info["scanned_pages"] and len(info["scanned_pages"]) > 0.3 * max(1, info["pages"]):
        rep["problems"].append(f"{len(info['scanned_pages'])} of {info['pages']} pages have no text (scanned): this PDF needs OCR first")
    fz = None
    img_pdf = Path(meta["source_pdf"]) if meta.get("source_pdf") else (pdf if pdf.suffix.lower() != ".md" else None)  # a markdown text has page images only when its PDF is named (same page numbers)
    if img_pdf is not None and not img_pdf.exists():
        rep.setdefault("notes", []).append(f"source_pdf not found: {img_pdf}")
        img_pdf = None
    if frozen_dir is not None and not rep["problems"] and img_pdf is not None:
        frozen_dir.mkdir(parents=True, exist_ok=True)
        fz = frozen_dir / f"{iid}_{_slug(img_pdf.stem)[:40]}.pdf"
        if not fz.exists():
            shutil.copy2(img_pdf, fz)
            fz.chmod(0o444)
    skey = f"LAWPDF_{iid}"
    sha = _sha(img_pdf if (fz is not None and img_pdf is not None) else pdf)  # the check re-hashes the frozen file that `path` points to
    sdef = {"key": skey, "kind": meta.get("source_kind", "sgg_consolidated"), "edition": "official",  # the Arabic text of the law itself; where the copy came from is in "kind"
            "label": meta.get("source_label") or f"{meta.get('title_ar') or meta.get('title_fr') or number} ({pdf.name})", "sha256": sha,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if fz is not None:
        sdef["path"] = str(fz)
        sdef["url"] = fz.resolve().as_uri()  # the PDF page viewer finds the file here
    consolidated = meta.get("consolidated_on")
    note = (f"consolidated text read from {pdf.name}" + (f" (consolidated on {consolidated})" if consolidated else "")
            + "; amendments after that date are not in it; effective_date is the one given at import: check it")
    inst = {
        "instrument_id": iid, "kind": kind, "number": number, "short_code": meta.get("short_code") or number,
        "title_ar": meta.get("title_ar"), "title_fr": meta.get("title_fr"), "bo_number": meta.get("bo_number"), "bo_date": meta.get("bo_date"),
        "promulgation_date": meta.get("promulgation"), "effective_date": effective, "domain": meta.get("domain", "other"),
        "language_availability": {lang: "official"}, "status_note": note, "consolidated_text_available": True, "official_article_count": meta.get("official_articles"),
    }
    provs = []
    for a in arts:
        if not a.body:
            rep.setdefault("empty_articles", []).append(a.number)
            continue
        prov = {
            "instrument_id": iid, "number": a.number, "path": a.path, "page": a.page, "page_end": a.page_end,
            "versions": [{"valid_from": effective or "1900-01-01", "valid_to": None, "source": skey, "controlling_lang": lang, "texts": {lang: {"text": a.body, "edition": "official"}}}],
        }
        if not a.number.split()[0].isdigit():
            prov["provision_id"] = f"{iid}_ART_{_slug(a.number)}"
        provs.append(prov)
    src = {"sources": [sdef], "instruments": [inst], "provisions": provs, "edges": []}
    rep["instrument_id"], rep["articles"] = iid, len(provs)
    rep["first"] = (provs[0]["number"], provs[0]["versions"][0]["texts"][lang]["text"][:100]) if provs else None
    rep["last"] = (provs[-1]["number"], provs[-1]["versions"][0]["texts"][lang]["text"][:100]) if provs else None
    return src, rep


# =================================================================================================================== install / CLI
def print_report(rep: dict, out=sys.stdout) -> None:
    w = lambda *a: print(*a, file=out)  # noqa: E731
    w(f"instrument       {rep.get('instrument_id')}")
    w(f"pages            {rep.get('pages')}  (no text on {len(rep.get('scanned_pages') or [])}: {rep.get('scanned_pages')[:15] if rep.get('scanned_pages') else 'none'})")
    w(f"text order       {'WAS BACKWARDS in the PDF: repaired' if rep.get('reversed') else 'normal'}")
    w(f"article word     {rep.get('article_word')}    furniture lines dropped: {rep.get('furniture_lines_dropped')}")
    w(f"ARTICLES FOUND   {rep.get('articles')}")
    if rep.get("first"):
        w(f"  first: {rep['first'][0]}  {rep['first'][1]}")
        w(f"  last : {rep['last'][0]}  {rep['last'][1]}")
    gaps = rep.get("gaps") or []
    if rep.get("toc_discarded"):
        w(f"table of contents  {rep['toc_discarded']} heading-only entries found before the text and discarded")
    w(f"numbering gaps   {len(gaps)}  {gaps[:20]}")
    if rep.get("duplicates"):
        w(f"repeated numbers {rep['duplicates'][:20]}  (kept the longest text)")
    if rep.get("empty_articles"):
        w(f"empty articles   {rep['empty_articles'][:20]}")
    ref = rep.get("refused_headings") or []
    w(f"headings refused {len(ref)}  (lines that look like an article heading but break the numbering: left inside the previous article)")
    for r in ref[:8]:
        w(f"    p.{r['page']}: {r['line']}   [{r['why']}]")
    for p in rep.get("problems") or []:
        w(f"PROBLEM  {p}")


def install(src: dict, ctx) -> dict:
    """Add the sources to the installed pack (same path as the update button: work on a copy, append, verify, swap)."""
    from ..bo_update import discover  # noqa: F401 (keeps import order of the package stable)
    from ..state import install_pack
    from ..store.localkey import local_private_key
    from .append import append_sources

    s = ctx.settings
    dest = s.resolved_lawpack_path()
    iid = src["instruments"][0]["instrument_id"]
    if iid in ctx.pack.instrument_ids():
        raise RuntimeError(f"{iid} is already in the pack; use another --number / --kind, or remove it first")
    work = dest.with_name("update-work.db")
    shutil.copy2(dest, work)
    work.with_suffix(".db.sig").unlink(missing_ok=True)
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-law"
    key = local_private_key(s) if (ctx.pack_trust and ctx.pack_trust.state == "signed_valid") else None
    try:
        res = append_sources(work, src, ctx.embedder(), version, key, progress=lambda k, d, t: print(f"\r  {k} {d}/{t}", end="", flush=True))
        print()
        install_pack(ctx, work, work.with_suffix(".db.sig") if work.with_suffix(".db.sig").exists() else None)
    finally:
        work.unlink(missing_ok=True)
        work.with_suffix(".db.sig").unlink(missing_ok=True)
    res["pack_version"] = version
    return res


def run_batch(path: Path, do_install: bool) -> int:
    import sqlite3

    """Many laws in one go: each entry is read and reported; with --install the good ones are added one after the other, the others are listed."""
    import json

    from ..config import Settings
    from ..state import build_context

    entries = json.loads(path.read_text("utf-8"))
    s = Settings()
    ctx = build_context(s) if do_install else None
    if ctx is not None and not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    summary: list[tuple[str, str]] = []
    pack_db = None
    if any(e.get("if_absent") for e in entries) and s.resolved_lawpack_path().exists():
        pack_db = sqlite3.connect(f"file:{s.resolved_lawpack_path()}?mode=ro", uri=True)
    for e in entries:
        f = e.get("file")
        name = f"{e.get('number')} {e.get('title') or e.get('title_fr') or ''}".strip()[:90]
        if e.get("if_absent") and pack_db is not None and pack_db.execute("SELECT 1 FROM instrument WHERE number=? LIMIT 1", (str(e.get("number")),)).fetchone():
            summary.append((name, "SKIPPED: already in the pack (compare with crosscheck_sgg)"))
            continue
        print("=" * 78 + f"\n{name}   <- {f}")
        if not f or not Path(f).exists():
            summary.append((name, "SKIPPED: file not found"))
            print("  file not found")
            continue
        meta = {"number": e["number"], "title_ar": e.get("title"), "title_fr": e.get("title_fr"), "kind": e.get("kind", "law"), "lang": e.get("lang", "ar"),
                "effective": e.get("effective"), "promulgation": e.get("promulgation"), "bo_number": e.get("bo_number"), "bo_date": e.get("bo_date"),
                "consolidated_on": e.get("consolidated_on"), "domain": e.get("domain", "other"), "short_code": e.get("short_code"),
                "article_word": e.get("article_word"), "source_pdf": e.get("source_pdf"), "source_kind": e.get("source_kind", "sgg_consolidated"), "official_articles": e.get("official_articles"), "min_articles": e.get("min_articles", 3),
                "id_suffix": e.get("id_suffix")}
        try:
            src, rep = law_pdf_to_sources(Path(f), meta, (s.resolved_bo_dir() / "frozen" / "laws") if do_install else None)
        except Exception as ex:  # noqa: BLE001
            summary.append((name, f"FAILED to read: {ex.__class__.__name__}: {ex}"))
            continue
        print_report(rep)
        if rep["problems"]:
            summary.append((name, "NOT ADDED: " + rep["problems"][0]))
            continue
        flag = f" (expected {e['official_articles']})" if e.get("official_articles") and e["official_articles"] != rep["articles"] else ""
        if not do_install:
            summary.append((name, f"ok, {rep['articles']} articles{flag} (report only)"))
            continue
        try:
            res = install(src, ctx)
            summary.append((name, f"ADDED {res['articles']} articles{flag}"))
            ctx = build_context(s)  # the pack on disk changed
            if pack_db is not None:
                pack_db.close()
                pack_db = sqlite3.connect(f"file:{s.resolved_lawpack_path()}?mode=ro", uri=True)
        except Exception as ex:  # noqa: BLE001
            summary.append((name, f"NOT ADDED: {ex}"))
    print("\n" + "=" * 78 + "\nSUMMARY")
    for n, r in summary:
        print(f"  {n}: {r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m legalrag.builder.from_law_pdf", description=__doc__.split("\n\n")[0])
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--batch", help="a JSON file listing many laws: [{\"file\": \"C:/laws/65.99.pdf\", \"number\": \"65.99\", \"title\": \"مدونة الشغل\", \"effective\": \"2004-06-08\", \"domain\": \"labor\"}, ...]")
    ap.add_argument("--number", help="the law number as written, e.g. 65.99 (the Constitution: 2011)")
    ap.add_argument("--title", help="Arabic title, e.g. مدونة الشغل")
    ap.add_argument("--title-fr", help="French title")
    ap.add_argument("--kind", choices=sorted(KINDS), default="law")
    ap.add_argument("--lang", choices=["ar", "fr"], default="ar")
    ap.add_argument("--effective", help="YYYY-MM-DD the text enters into force")
    ap.add_argument("--promulgation", help="YYYY-MM-DD of the dahir")
    ap.add_argument("--bo-number")
    ap.add_argument("--bo-date")
    ap.add_argument("--consolidated-on", help="YYYY-MM-DD the PDF's text is up to date at")
    ap.add_argument("--domain", choices=DOMAINS, default="other")
    ap.add_argument("--short-code", help="e.g. 65.99 (defaults to the number)")
    ap.add_argument("--source-kind", choices=["sgg_consolidated", "adala", "bo_pdf", "other"], default="sgg_consolidated")
    ap.add_argument("--official-articles", type=int, help="the real number of articles, to compare with what was found")
    ap.add_argument("--article-word", help="force the heading word (المادة or الفصل), e.g. for a law that quotes amended Penal Code chapters")
    ap.add_argument("--min-articles", type=int, default=3)
    ap.add_argument("--dump", help="write the articles to this text file so you can read them")
    ap.add_argument("--install", action="store_true", help="add to the pack (stop the backend first); without it only the report is printed")
    a = ap.parse_args(argv)
    if a.batch:
        return run_batch(Path(a.batch), a.install)
    if not a.pdf or not a.number:
        ap.error("give the PDF and --number (or --batch FILE.json)")
    meta = {"number": a.number, "title_ar": a.title, "title_fr": a.title_fr, "kind": a.kind, "lang": a.lang, "effective": a.effective, "promulgation": a.promulgation,
            "bo_number": a.bo_number, "bo_date": a.bo_date, "consolidated_on": a.consolidated_on, "domain": a.domain, "short_code": a.short_code,
            "source_kind": a.source_kind, "official_articles": a.official_articles, "min_articles": a.min_articles, "article_word": a.article_word}
    from ..config import Settings

    s = Settings()
    frozen = (s.resolved_bo_dir() / "frozen" / "laws") if a.install else None
    src, rep = law_pdf_to_sources(Path(a.pdf), meta, frozen)
    print_report(rep)
    if a.official_articles and rep["articles"] != a.official_articles:
        print(f"WARNING  {rep['articles']} articles found, {a.official_articles} expected")
    if a.dump:
        with open(a.dump, "w", encoding="utf-8") as f:
            for p in src["provisions"]:
                f.write(f"=== {p['number']}   (p.{p['page']})   {p['path'] or ''}\n{p['versions'][0]['texts'][meta['lang']]['text']}\n\n")
        print(f"articles written to {a.dump}")
    if rep["problems"]:
        return 2
    if not a.install:
        print("\nReport only. Read it, then add --install to put the law in the pack (stop the backend first, restart it after).")
        return 0
    from ..state import build_context

    ctx = build_context(s)
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    res = install(src, ctx)
    print(f"added: {res['instruments']} law, {res['articles']} articles, {res['chunks']} passages  (pack {res['pack_version']}). Restart the backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
