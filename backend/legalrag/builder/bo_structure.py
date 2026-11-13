# Vendored from the BO pipeline (chunk_bo.py, with the article-number fixes of the same date): structure-aware parsing of extracted Bulletin Officiel markdown.
# from_bo.py imports its parse functions; its own chunking is not used by the law-pack builder.
#!/usr/bin/env python3
"""
chunk_bo.py  --  structure-aware chunking of Bulletin Officiel (Arabic) markdown for RAG.

Input : the .md files written by extract_bo_pdf.py (a file, or a folder -> all sub-folders).
Output: <name>.chunks.jsonl next to every .md (or all in one folder with --out-dir)   (one JSON object per chunk)  [+ --combined all.jsonl] [+ --preview]

Why not fixed-size windows?  A BO issue is a stack of independent legal texts (decrees, orders, decisions ...).
A fixed window glues the end of one decree to the start of the next, cuts an article in half and separates a
table from its title.  This script instead
  1. cleans the page furniture (running headers, "صفحة", stray marks) and drops the contents/cover pages,
  2. finds every legal text (type + number + dates + subject, from its bold title),
  3. splits each text on its own structure: preamble (visas) / articles / chapters / annexes / tables,
  4. packs whole articles into chunks of ~target tokens (small texts stay in ONE chunk), only an article longer
     than max is cut, on sentence boundaries, with overlap,
  5. tables are separate chunks, rows grouped with the header row repeated,
  6. every chunk carries a context header (issue, date, section, title, article range) in `embed_text`, and
     metadata (type, number, dates, pages, article numbers, referenced texts, prev/next id, quality flags).

Embed `embed_text`, show/quote `content`, filter on the metadata.   No third-party packages needed.
Usage:  python chunk_bo.py FOLDER_OR_FILE.md [--target 400 --max 650 --min 60 --overlap 60]
                         [--combined all.jsonl] [--keep-toc] [--with-norm] [--preview] [--tokenizer hf:BAAI/bge-m3]
"""
from __future__ import annotations
import argparse, hashlib, json, math, re, sys, unicodedata
from pathlib import Path

# ----------------------------------------------------------------------------- vocabulary
TYPE_WORDS = r"(?:ظهير شريف|ظهير|مرسوم بقانون|مرسوم|قرار|مقرر|قانون تنظيمي|قانون إطار|قانون|دورية|بلاغ|رأي|اتفاقية|اتفاق|منشور|نظام|تصريح|إعلان|حكم|أمر)"
TYPE_RE = re.compile(rf"^{TYPE_WORDS}(?=\s|$)")
SECTION_RE = re.compile(r"^(نصوص عامة|نصوص خاصة|إعلانات وبلاغات|نشرة الترجمة الرسمية|نشرة الاتفاقيات الدولية|"
                        r"نشرة الإعلانات القانونية والقضائية والإدارية|نشرة الإعلانات المتعلقة بالتحفيظ العقاري|"
                        r"(?:القسم|الجزء) (?:الأول|الثاني|الثالث|الرابع))\s*[.:]?$")
ARTICLE_LINE = re.compile(r"^(المادة|الفصل)\s+(\S+(?:\s+\S+){0,2}?)\s*[:：]?\s*$")
ARTICLE_RUNIN = re.compile(r"^(المادة|الفصل)\s+((?:ال[أإا]ول[ىي]|ال\w+(?:\s+(?:عشر[ة]?|و?ال\w+))?|[\d٠-٩]+(?:[.\-][\d٠-٩]+)*)"
                           r"(?:\s+(?:مكرر[ةا]?(?:\s+مرتين)?|ثالثا|رابعا|خامسا))?)\s*[:：\-–]\s+(\S.*)$")
BAD_LABEL_WORDS = {"من", "في", "إلى", "على", "أعلاه", "المشار", "و", "عن", "بعد", "قبل", "هذا", "هذه", "السالف", "المذكور", "المذكورة"}
CHAPTER_RE = re.compile(r"^(الباب|القسم|الجزء|الفرع|الكتاب|العنوان)\s+(\S+(?:\s+\S+){0,2})\s*[:：]?$")
PREAMBLE_END = re.compile(r"(رسم ما يلي|يرسم ما يلي|قرر ما يلي|يقرر ما يلي|قررنا ما يلي|أصدرنا أمرنا الشريف|يصدر هذا القرار|نقرر ما يلي)")
SIGN_START = re.compile(r"^(الإمضاء|وقعه بالعطف|وقعه|وحرر بـ?|حرر بـ?|وحرر|وقع)")
FURNITURE = [
    re.compile(r"^\d{1,4}\s+الجريدة الرسمية\s+عدد\s+\d+.*$"),
    re.compile(r"^عدد\s+\d+\s*[-–]\s*.*الجريدة الرسمية\s+\d{1,4}\s*$"),
    re.compile(r"^(صفحة\s*)+$"),
    re.compile(r"^الجريدة الرسمية\s+\d{1,4}$"),
]
TOC_TAIL = re.compile(r"(…|\.{3,}|\.\.)\s*\d{1,4}\s*$")
ORD = {"الأولى": 1, "الأول": 1, "الثانية": 2, "الثاني": 2, "الثالثة": 3, "الثالث": 3, "الرابعة": 4, "الرابع": 4, "الخامسة": 5,
       "الخامس": 5, "السادسة": 6, "السادس": 6, "السابعة": 7, "السابع": 7, "الثامنة": 8, "الثامن": 8, "التاسعة": 9, "التاسع": 9,
       "العاشرة": 10, "العاشر": 10}
REF_RE = re.compile(r"(الظهير الشريف|المرسوم(?: بقانون| التطبيقي)?|القرار(?: المشترك)?|القانون(?: التنظيمي| الإطار)?|المقرر|الدورية)\s+رقم\s+([\d]+(?:[.\-/]\d+)*)")
DATE_RE = re.compile(r"(\d{1,2}|فاتح)\s+(?:من\s+)?(محرم|صفر|ربيع الأول|ربيع الآخر|جمادى الأولى|جمادى الآخرة|رجب|شعبان|رمضان|شوال|ذو القعدة|ذو الحجة)\s+(\d{4})")
GREG_RE = re.compile(r"\((\d{1,2}|فاتح)\s+([^\d()]+?)\s*(\d{4})\)")
NOTE_RE = re.compile(r"^>\s*\*\*NOTE:\*\*\s*(.*)$")

_TATWEEL = re.compile("[ـ​-‏‪-‮⁦-⁩﻿]")


def clean_text(s: str) -> str:
    s = _TATWEEL.sub("", s)
    s = re.sub(r"[ -   ]", " ", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def normalize_ar(s: str) -> str:
    """For BM25 / lexical search only (kept in a separate field): no diacritics, unified alef/yeh/heh."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[ً-ٰٟ]", "", s)
    s = re.sub("[إأآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", s).strip()


# ----------------------------------------------------------------------------- token estimate
class Tok:
    def __init__(self, spec: str | None):
        self.hf = None
        if spec and spec.startswith("hf:"):
            from transformers import AutoTokenizer          # optional dependency
            self.hf = AutoTokenizer.from_pretrained(spec[3:])

    def __call__(self, text: str) -> int:
        if self.hf is not None:
            return len(self.hf.encode(text, add_special_tokens=False))
        # Arabic: ~1.6 sub-word tokens per word, digits/Latin a bit more; good enough for budgeting
        return int(math.ceil(len(text.split()) * 1.6))


# ----------------------------------------------------------------------------- 1. parse markdown
def parse_md(text: str):
    """-> list of elements {kind: heading|para|table, text, page}, plus page notes {page: [..]}"""
    els, notes, page = [], {}, 0
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        m = re.match(r"^<!--\s*page\s+(\d+)\s*-->$", ln.strip())
        if m:
            page = int(m.group(1)); i += 1; continue
        if ln.strip() in ("---", ""):
            i += 1; continue
        m = NOTE_RE.match(ln.strip())
        if m:
            notes.setdefault(page, []).append(m.group(1)); i += 1; continue
        if ln.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            els.append({"kind": "table", "text": "\n".join(l.rstrip() for l in lines[i:j]), "page": page}); i = j; continue
        if ln.startswith("## "):
            els.append({"kind": "heading", "text": clean_text(ln[3:]), "page": page}); i += 1; continue
        els.append({"kind": "para", "text": clean_text(ln), "page": page}); i += 1
    return els, notes


def drop_furniture(els):
    out = []
    for e in els:
        if e["kind"] != "table":
            t = e["text"]
            if not t or re.fullmatch(r"[*\s]+", t):
                continue
            if len(t) < 170 and any(r.match(t) for r in FURNITURE):
                continue
            if len(t) <= 2 and not re.search(r"\d", t):      # stray accent / mark that landed on its own line
                continue
        out.append(e)
    return out


def merge_headings(els):
    """A bold title wrapped over several lines arrives as several '##' lines: re-join them, but never merge a
    heading that ends a sentence (topic line) or one that starts a new legal text / section."""
    out = []
    for e in els:
        p = out[-1] if out else None
        if (e["kind"] == "heading" and p and p["kind"] == "heading" and not SECTION_RE.match(p["text"])
                and not p["text"].rstrip().endswith((".", ":", "؛")) and not TYPE_RE.match(e["text"])
                and not SECTION_RE.match(e["text"]) and not re.match(r"^(ملحق|جدول|لائحة)", e["text"])):
            p["text"] = p["text"].rstrip() + " " + e["text"]
        else:
            out.append(dict(e))
    return out


def drop_toc(els, notes, keep=False):
    """Cover / contents pages: most paragraphs end with '… 31' (page reference).  They duplicate the real texts."""
    by = {}
    for e in els:
        by.setdefault(e["page"], []).append(e)
    toc_pages = set()
    for pg, es in by.items():
        nt = [e for e in es if e["kind"] != "table"]
        hits = sum(bool(TOC_TAIL.search(e["text"])) for e in nt)
        if pg <= 8 and hits >= 3 and hits >= 0.15 * len(nt):         # contents / cover pages sit at the very front
            toc_pages.add(pg)
    if keep:
        return els, toc_pages
    return [e for e in els if e["page"] not in toc_pages], toc_pages


# ----------------------------------------------------------------------------- 2. issue metadata
def issue_meta(text: str, fname: str):
    meta = {"number": None, "date_hijri": None, "date_gregorian": None}
    # "عدد 7079 - 2 رمضان 1443 (4 أبريل 2022)": the dash is often missing, and special issues say "عدد 7040 مكرر 12 ربيع الآخر ..."
    m = re.search(r"عدد\s+(\d{3,5})((?:\s*[-–]\s*bis)|(?:\s+مكرر))?\s*[-–]?\s*([^()\n]+?)\s*\(([^)]+)\)", text)
    if m:
        meta["number"] = m.group(1) + ("-bis" if m.group(2) else ""); meta["date_hijri"] = m.group(3).strip(); meta["date_gregorian"] = m.group(4).strip()
    if not meta["number"]:
        n = re.search(r"BO[_-]?(\d{4}(?:-bis)?)", fname)
        meta["number"] = n.group(1) if n else Path(fname).stem
    return meta


def parse_title(title: str):
    t = {"doc_type": None, "doc_number": None, "doc_date_hijri": None, "doc_date_gregorian": None, "subject": None}
    m = TYPE_RE.match(title)
    if m:
        # keep qualifiers such as "قرار مشترك" / "قرار لوزير ..." as free text; type is the head word(s)
        t["doc_type"] = m.group(0)
    n = re.search(r"(?:رقم|عدد)\s+([\d]+(?:[.\-/][0-9A-Za-z]+)*(?:/ق/\d+)?)", title)  # not \w: "1432.22صادر" (no space before the next word) must stay "1432.22"
    if n:
        t["doc_number"] = n.group(1)
    d = re.search(r"صادر\w*\s+في\s+(.+?)\s*\(([^)]*\d{4})\)", title)
    if d:
        t["doc_date_hijri"] = d.group(1).strip(); t["doc_date_gregorian"] = d.group(2).strip()
    else:
        d2 = DATE_RE.search(title)
        if d2:
            t["doc_date_hijri"] = d2.group(0)
    s = re.search(r"\)\s*(ب\S.*|يقضي.*|المتعلق.*|القاضي.*)$", title)
    t["subject"] = (s.group(1) if s else title)[:400]
    return t


# ----------------------------------------------------------------------------- 3. split into legal units
def is_label_only(line: str, rx):
    m = rx.match(line)
    if not m or len(line) > 48:
        return None
    words = set(line.split())
    return m if not (words & BAD_LABEL_WORDS) else None


def article_start(line: str):
    """-> (label, remainder) when the line opens an article, else None.  Quoted amendments («المادة 2.13 ...) are not."""
    if line[:1] in "«\"“'":
        return None
    m = ARTICLE_RUNIN.match(line)            # first: "المادة 4 : تلغى" is a run-in article, not a 3-word label
    if m:
        return f"{m.group(1)} {m.group(2).strip()}", m.group(3)
    m = is_label_only(line, ARTICLE_LINE)
    if m:
        return f"{m.group(1)} {m.group(2).strip()}", ""
    return None


# ---- article numbers: digits, Arabic-Indic digits, ordinals ("الثانية عشرة" = 12, "الحادية والعشرون" = 21), suffixes (مكرر ...)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_ORD_UNITS = {"اول": 1, "اولي": 1, "حادي": 1, "حاديه": 1, "ثان": 2, "ثاني": 2, "ثانيه": 2, "ثالث": 3, "ثالثه": 3, "رابع": 4, "رابعه": 4,
              "خامس": 5, "خامسه": 5, "سادس": 6, "سادسه": 6, "سابع": 7, "سابعه": 7, "ثامن": 8, "ثامنه": 8, "تاسع": 9, "تاسعه": 9}
_ORD_TENS = {"عاشر": 10, "عاشره": 10, "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "اربعين": 40,
             "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60, "سبعون": 70, "سبعين": 70, "ثمانون": 80, "ثمانين": 80,
             "تسعون": 90, "تسعين": 90}
_SUFFIX_WORDS = {"مكرر", "مكررة", "مكررا", "مرتين", "ثالثا", "رابعا", "خامسا"}


def _ord_stem(w: str) -> str:
    w = re.sub("[إأآٱ]", "ا", w).replace("ى", "ي").replace("ة", "ه")
    w = re.sub(r"^و", "", w)
    return re.sub(r"^ال", "", w)


def _split_label(label: str):
    """'المادة الثانية عشرة مكررة' -> (['الثانية', 'عشرة'], ['مكررة'])"""
    toks = label.split()[1:]
    for i, t in enumerate(toks):
        if t in _SUFFIX_WORDS:
            return toks[:i], toks[i:]
    return toks, []


def article_no(label: str):
    """The plain integer of the article (suffix ignored) or None (dotted numbers like 2.13, unreadable words)."""
    num, _ = _split_label(label)
    if len(num) == 1 and re.fullmatch(r"[\d٠-٩]+", num[0]):
        return int(num[0].translate(_DIGITS))
    total, seen = 0, False
    for w in num:
        s = _ord_stem(w)
        if s in ("عشره", "عشر") and seen:
            total += 10
        elif s in _ORD_TENS:
            total += _ORD_TENS[s]; seen = True
        elif s in _ORD_UNITS:
            total += _ORD_UNITS[s]; seen = True
        elif s == "":
            continue
        else:
            return None
    return total if seen and total else None


def article_id(label: str):
    """Unique text key of the article inside its law: '5', '5 مكرر', '5 مكرر مرتين', '2.13', '12' (for الثانية عشرة).
    Use this, not the integer, to tell article 5 from article 5 bis."""
    num, suf = _split_label(label)
    n = article_no(label)
    base = str(n) if n is not None else " ".join(num).translate(_DIGITS)
    suf = [("مكرر" if s in ("مكررة", "مكررا") else s) for s in suf]
    return (base + (" " + " ".join(suf) if suf else "")).strip()


STRONG_START = re.compile(rf"^{TYPE_WORDS}(?:\s+\S+){{0,6}}?\s+(?:رقم|عدد)\s+[\d./]+\S*\s+صادر\w*\s+في\s")


def split_units(els, issue):
    units, cur, section, pending, pend_sec = [], None, None, [], None
    recent_sign = 0

    def new_unit(title, topic):
        nonlocal cur, recent_sign
        cur = {"title": title, "topic": topic, "section": section, "els": [], "page": None}
        units.append(cur); recent_sign = 0

    k = 0
    while k < len(els):
        e = els[k]
        if e["kind"] == "heading":
            t = e["text"]
            if SECTION_RE.match(t):
                section = SECTION_RE.match(t).group(1); cur = None; pending = []; k += 1; continue   # a new section ends the previous text
            if TYPE_RE.match(t) and re.search(r"(رقم|عدد)\s+\d", t[:120]):
                new_unit(t, " | ".join(pending) or None); cur["page"] = e["page"]; pending = []; k += 1; continue
            nxt = els[k + 1] if k + 1 < len(els) else None
            if nxt and nxt["kind"] == "heading" and TYPE_RE.match(nxt["text"]) and t.rstrip().endswith("."):
                pending.append(t.rstrip(". ")); k += 1; continue                 # topic line printed above a title
            if nxt and nxt["kind"] == "heading" and t.rstrip().endswith(".") and not TYPE_RE.match(t) and len(t) < 90 \
                    and re.match(r"^(وزارة|الوزارة|الأمانة|المجلس|الهيئة|المندوبية|رئاسة|إقليم|عمالة|جماعة|نظام)", t):
                pending.append(t.rstrip(". ")); k += 1; continue                 # issuing body above a title
        elif e["kind"] == "para" and cur is not None and recent_sign and STRONG_START.match(e["text"]) and len(e["text"]) < 700:
            new_unit(e["text"], " | ".join(pending) or None); cur["page"] = e["page"]; pending = []; k += 1; continue
        if cur is None:
            new_unit(e["text"] if e["kind"] == "heading" else None, None); cur["page"] = e["page"]
            if e["kind"] == "heading":
                k += 1; continue
        cur["els"].append(e)
        if e["kind"] == "para":
            recent_sign = 6 if SIGN_START.match(e["text"]) else max(recent_sign - 1, 0) if recent_sign else 0
        k += 1
    return units


# ----------------------------------------------------------------------------- 4. unit -> parts
def split_parts(unit):
    """Break one legal text into atomic parts: preamble, articles, annex blocks, tables.  A chapter heading
    (الباب/القسم ...) becomes metadata and is also kept as the first line of the part that follows it."""
    parts, state = [], {"chapter": None, "annex": None, "carry": []}

    def new(kind, label, page, **kw):
        p = {"kind": kind, "label": label, "lines": list(state["carry"]), "page": page, "page_end": page,
             "chapter": state["chapter"], "annex": state["annex"], **kw}
        state["carry"] = []
        parts.append(p)
        return p

    cur = new("preamble", None, unit["page"])
    els = unit["els"]
    k = 0
    while k < len(els):
        e = els[k]
        t = e["text"]
        if e["kind"] == "table":
            cap = None
            if cur["kind"] != "table" and cur["lines"] and len(cur["lines"][-1]) < 220 and not cur["lines"][-1].endswith("."):
                cap = cur["lines"].pop()                       # short line right above a table = its caption
            lab = cur["label"]
            new("table", lab, e["page"], caption=cap, table=t)
            parts[-1]["page_end"] = e["page"]
            cur = new("continuation", lab, e["page"])         # text after the table goes on in the same article
            k += 1; continue
        if e["kind"] == "heading" and re.match(r"^(ملحق|جدول|لائحة|بيان|قائمة|تصميم)", t):
            state["annex"] = t
            cur = new("annex", None, e["page"]); cur["lines"].append(t)
            k += 1; continue
        if e["kind"] == "para":
            a = article_start(t)
            if a:
                cur = new("article", a[0], e["page"], number=article_no(a[0]), art_id=article_id(a[0]))
                if a[1]:
                    cur["lines"].append(a[1])
                k += 1; continue
            ch = is_label_only(t, CHAPTER_RE)
            if ch:
                title = ""
                if k + 1 < len(els) and els[k + 1]["kind"] in ("heading", "para") and len(els[k + 1]["text"]) < 90 \
                        and not article_start(els[k + 1]["text"]):
                    title = " - " + els[k + 1]["text"]; k += 1
                state["chapter"] = (t + title).strip()
                state["carry"].append(state["chapter"])
                cur = new("continuation", None, e["page"]); k += 1; continue
        cur["lines"].append(t); cur["page_end"] = e["page"]
        k += 1
    out = []
    for p in parts:
        if p["kind"] == "table":
            out.append(p); continue
        if not "\n".join(p["lines"]).strip():
            continue
        if p["kind"] == "continuation" and out and out[-1]["kind"] in ("article", "preamble", "annex") \
                and not (p["lines"][0] == state.get("chapter") or CHAPTER_RE.match(p["lines"][0])):
            out[-1]["lines"] += p["lines"]; out[-1]["page_end"] = p["page_end"]; continue
        out.append(p)
    return out


# ----------------------------------------------------------------------------- 5. packing
SENT_SPLIT = re.compile(r"(?<=[.؟?!؛;:])\s+(?=\S)|(?<=\S)\s+(?=\d{1,4}\s*[-–]\s*[^\d\s])|(?<=\))\s+(?=[وف]?على\s|[وف]?بعد\s|[وف]?بناء\s)")


def split_long(text: str, tok: Tok, max_t: int, overlap: int):
    """Cut an over-long block at sentence boundaries, with a sentence-level overlap."""
    sents = [s.strip() for s in SENT_SPLIT.split(text.replace("\n", "\n ")) if s.strip()]
    if len(sents) <= 1:
        sents = text.split()
        join = " "
    else:
        join = " "
    flat = []
    for s in sents:                                       # one "sentence" longer than the limit: cut on words
        if tok(s) > max_t:
            w = s.split()
            step = max(int(len(w) * max_t / max(tok(s), 1)), 20)
            ov = max(int(step * overlap / max(max_t, 1)), 0)
            i = 0
            while i < len(w):
                flat.append(" ".join(w[i:i + step]))
                if i + step >= len(w):
                    break
                i += step - ov
        else:
            flat.append(s)
    sents = flat
    pieces, cur, cur_t = [], [], 0
    for s in sents:
        st = tok(s)
        if cur and cur_t + st > max_t:
            pieces.append(join.join(cur))
            keep, kt = [], 0
            for x in reversed(cur):                       # overlap = last sentences up to `overlap` tokens
                xt = tok(x)
                if kt + xt > overlap:
                    break
                keep.insert(0, x); kt += xt
            cur, cur_t = keep, kt
        cur.append(s); cur_t += st
    if cur:
        pieces.append(join.join(cur))
    return pieces


def looks_header(row: str) -> bool:
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    return bool(cells) and not any(re.fullmatch(r"[\d\s.,/\-]+", c) or re.search(r"\d{5,}", c) for c in cells)


def table_pieces(tbl: str, tok: Tok, max_t: int):
    """Row groups; the header row is repeated in every piece only when the first row really is a header
    (the markdown always draws a header line, even for tables that have none)."""
    rows = tbl.splitlines()
    if len(rows) < 3:
        return [tbl]
    if looks_header(rows[0]):
        head, body = rows[:2], rows[2:]
    else:
        head, body = [], [rows[0]] + rows[2:]              # headerless table: drop the fake separator line
    ht = tok("\n".join(head)) if head else 0
    out, cur, ct = [], [], ht
    for r in body:
        rt = tok(r)
        if cur and ct + rt > max_t:
            out.append("\n".join(head + cur)); cur, ct = [], ht
        cur.append(r); ct += rt
    if cur:
        out.append("\n".join(head + cur))
    return out


def build_chunks(unit_parts, tok: Tok, target, max_t, min_t, overlap):
    """-> list of chunk dicts {content, kind, labels, pages, chapter, annex}"""
    items = []                                           # atomic items (already <= max_t)
    for p in unit_parts:
        if p["kind"] == "table":
            cap = (p.get("caption") or "")
            for i, piece in enumerate(table_pieces(p["table"], tok, max_t - tok(cap))):
                items.append({"kind": "table", "text": (cap + "\n" if cap else "") + piece, "label": p.get("label"),
                              "page": p["page"], "page_end": p["page_end"], "chapter": p["chapter"], "annex": p["annex"]})
            continue
        txt = "\n".join(p["lines"]).strip()
        lab = p["label"]
        full = (lab + "\n" if lab and p["kind"] == "article" else "") + txt
        if tok(full) <= max_t:
            items.append({"kind": p["kind"], "text": full, "label": lab, "page": p["page"], "page_end": p["page_end"],
                          "chapter": p["chapter"], "annex": p["annex"], "number": p.get("number"), "art_id": p.get("art_id")})
        else:
            for i, piece in enumerate(split_long(txt, tok, max_t - (tok(lab) if lab else 0), overlap)):
                head = (f"{lab} (تابع)\n" if lab and i else (lab + "\n" if lab else ""))
                items.append({"kind": p["kind"], "text": head + piece, "label": lab, "page": p["page"], "page_end": p["page_end"],
                              "chapter": p["chapter"], "annex": p["annex"], "number": p.get("number"), "art_id": p.get("art_id"), "split": True})
    total = sum(tok(i["text"]) for i in items)
    chunks, cur, ct = [], [], 0

    def flush():
        nonlocal cur, ct
        if cur:
            chunks.append(cur); cur, ct = [], 0

    if total <= max_t and not any(i["kind"] == "table" for i in items):
        cur = items; ct = total; flush()                 # a whole small text = one chunk
        return [pack(c) for c in chunks]
    for it in items:
        t = tok(it["text"])
        if it["kind"] == "table":
            flush(); chunks.append([it]); continue
        if it.get("split"):
            flush(); chunks.append([it]); continue
        if cur and (ct + t > max_t or (ct >= target) or (ct >= min_t and ct + t > target and not cur[-1]["kind"] == "preamble")):
            flush()
        if cur and cur[-1]["kind"] == "table":
            flush()
        cur.append(it); ct += t
    flush()
    # a tiny trailing chunk (signature, a one-line article) joins its predecessor when it fits
    merged = []
    for c in chunks:
        ctxt = sum(tok(i["text"]) for i in c)
        if merged and ctxt < min_t and sum(tok(i["text"]) for i in merged[-1]) + ctxt <= max_t:
            merged[-1].extend(c)
        else:
            merged.append(c)
    return [pack(c) for c in merged]


def pack(items):
    kinds = {i["kind"] for i in items}
    arts = [i["label"] for i in items if i.get("label") and i["kind"] == "article"]
    nums = [i["number"] for i in items if i.get("number")]
    return {"content": "\n\n".join(i["text"] for i in items),
            "kind": "table" if kinds == {"table"} else ("mixed" if "table" in kinds else "text"),
            "articles": list(dict.fromkeys(arts)), "numbers": nums,
            "article_ids": list(dict.fromkeys(i["art_id"] for i in items if i.get("art_id") and i["kind"] == "article")),
            "pages": [min(i["page"] for i in items), max(i["page_end"] for i in items)],
            "chapter": next((i["chapter"] for i in items if i.get("chapter")), None),
            "annex": next((i["annex"] for i in items if i.get("annex")), None)}


# ----------------------------------------------------------------------------- 6. assemble records
def refs_in(text: str):
    seen, out = set(), []
    for m in REF_RE.finditer(text):
        k = (m.group(1), m.group(2))
        if k not in seen:
            seen.add(k); out.append({"type": m.group(1), "number": m.group(2)})
    return out


def process_md(path: Path, a, tok: Tok):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    src_sha = hashlib.sha256(raw).hexdigest()
    issue = issue_meta(text, path.name)
    els, notes = parse_md(text)
    els = drop_furniture(els)
    els, toc_pages = drop_toc(els, notes, a.keep_toc)
    els = merge_headings(els)
    units = split_units(els, issue)
    if not a.keep_toc:                                    # cover page: masthead, ISSN, subscription tariff
        units = [u for u in units if not (u["title"] is None and u["page"] is not None and u["page"] <= 2 and
                                          re.search(r"ISSN|تعريفة الاشتراك|الاشتراك من المطبعة", " ".join(e["text"] for e in u["els"])))]
    recs = []
    inum = str(issue["number"]).replace(" ", "")
    for ui, u in enumerate(units):
        parts = split_parts(u)
        if not parts:
            continue
        chunks = build_chunks(parts, tok, a.target, a.max, a.min, a.overlap)
        if not chunks:
            continue
        tinfo = parse_title(u["title"]) if u["title"] else {"doc_type": None, "doc_number": None, "doc_date_hijri": None,
                                                           "doc_date_gregorian": None, "subject": None}
        if not u["title"]:                       # untitled block (e.g. an announcement): use its first heading(s)
            hs = [e["text"] for e in u["els"] if e["kind"] == "heading"][:2]
            if hs:
                u["title"] = " - ".join(h.strip() for h in hs)
        title = u["title"] or "(نص بدون عنوان)"
        doc_id = f"BO{inum}:{ui:03d}" + (f":{tinfo['doc_type']}:{tinfo['doc_number']}" if tinfo["doc_number"] else "")
        all_text = "\n".join(c["content"] for c in chunks)
        refs = refs_in(all_text)
        n = len(chunks)
        for ci, c in enumerate(chunks):
            flags = sorted({f.split(" (")[0].split(":")[0] for pg in range(c["pages"][0], c["pages"][1] + 1) for f in notes.get(pg, [])})
            hdr = [f"الجريدة الرسمية عدد {inum}" + (f" — {issue['date_hijri']} ({issue['date_gregorian']})" if issue["date_hijri"] else "")]
            if u["section"]:
                hdr.append(u["section"])
            if u["topic"]:
                hdr.append(u["topic"])
            hdr.append(title if ci == 0 or len(title) <= 220 else title[:220].rsplit(" ", 1)[0] + " …")
            if c["chapter"]:
                hdr.append(c["chapter"])
            if c["annex"] and c["kind"] != "text":
                hdr.append(c["annex"])
            if len(c["articles"]) == 1:
                hdr.append(c["articles"][0])
            elif len(c["articles"]) > 1:
                hdr.append(f"{c['articles'][0]} → {c['articles'][-1]}")
            rec = {
                "chunk_id": f"BO{inum}-{ui:03d}-{ci:02d}", "doc_id": doc_id, "unit_index": ui, "chunk_index": ci, "chunk_count": n,
                "prev_id": f"BO{inum}-{ui:03d}-{ci - 1:02d}" if ci else None,
                "next_id": f"BO{inum}-{ui:03d}-{ci + 1:02d}" if ci + 1 < n else None,
                "issue_number": inum, "issue_date_hijri": issue["date_hijri"], "issue_date_gregorian": issue["date_gregorian"],
                "section": u["section"], "topic": u["topic"], "title": title,
                "doc_type": tinfo["doc_type"], "doc_number": tinfo["doc_number"],
                "doc_date_hijri": tinfo["doc_date_hijri"], "doc_date_gregorian": tinfo["doc_date_gregorian"],
                "chunk_type": c["kind"], "articles": c["articles"], "article_ids": c["article_ids"], "chapter": c["chapter"], "annex": c["annex"],
                "pages": c["pages"], "refs": refs if ci == 0 else [r for r in refs if r["number"] in c["content"]],
                "flags": flags, "tokens_est": tok(c["content"]), "source_file": path.name, "source_sha256": src_sha,
                "content": c["content"], "embed_text": "\n".join(hdr) + "\n\n" + c["content"],
            }
            if a.with_norm:
                rec["content_norm"] = normalize_ar(c["content"])
            recs.append(rec)
    return recs, {"units": len(units), "toc_pages": sorted(toc_pages)}


def write_preview(path: Path, recs):
    out = []
    for r in recs:
        out.append(f"### {r['chunk_id']}  [{r['chunk_type']}]  ص {r['pages'][0]}-{r['pages'][1]}  ~{r['tokens_est']} tok\n"
                   f"> {r['embed_text'].split(chr(10)+chr(10))[0].replace(chr(10), ' | ')}\n\n{r['content']}\n\n---\n")
    Path(f"{path.with_suffix('')}.chunks.md").write_text("\n".join(out), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Structure-aware chunking of BO markdown for RAG")
    ap.add_argument("path", help=".md file or folder (all sub-folders)")
    ap.add_argument("--target", type=int, default=None, help="preferred chunk size (tokens)")
    ap.add_argument("--max", type=int, default=None, help="hard maximum (tokens); only a single over-long article is cut")
    ap.add_argument("--min", type=int, default=None, help="smaller pieces are merged into a neighbour")
    ap.add_argument("--overlap", type=int, default=None, help="overlap (tokens) when one article must be cut")
    ap.add_argument("--keep-toc", action="store_true", help="keep contents/cover pages (dropped by default)")
    ap.add_argument("--with-norm", action="store_true", help="add content_norm (diacritics/alef/yeh normalised) for BM25")
    ap.add_argument("--combined", help="also write every chunk of every file into this one .jsonl")
    ap.add_argument("--out-dir", help="write every <name>.chunks.jsonl (and previews) into this one folder instead of next to each .md")
    ap.add_argument("--preview", action="store_true", help="also write <name>.chunks.md to eyeball the chunks")
    ap.add_argument("--tokenizer", help="hf:<model> to count real tokens (needs transformers), default: word-based estimate")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--profile", choices=["default", "bert512"], default="default",
                    help="bert512: smaller chunks (target 280 / max 400 / min 50 / overlap 40) so that header + text stay under "
                         "the 512-token limit of BERT-base embedding models such as dz-legal-ar-embeddings-v1")
    a = ap.parse_args()
    prof = {"default": (400, 650, 60, 60), "bert512": (280, 400, 50, 40)}[a.profile]
    for name, v in zip(("target", "max", "min", "overlap"), prof):
        if getattr(a, name) is None:
            setattr(a, name, v)
    tok = Tok(a.tokenizer)
    src = Path(a.path)
    files = sorted(p for p in src.rglob("*.md") if not p.name.endswith(".chunks.md")) if src.is_dir() else [src]
    if a.out_dir:
        Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    comb = open(a.combined, "w", encoding="utf-8") if a.combined else None
    tot = 0
    for f in files:
        out = Path(a.out_dir) / f"{f.stem}.chunks.jsonl" if a.out_dir else Path(f"{f.with_suffix('')}.chunks.jsonl")
        try:
            recs, st = process_md(f, a, tok)
        except Exception as e:
            print(f"FAILED {f}: {e!r}", file=sys.stderr); continue
        with open(out, "w", encoding="utf-8") as fh:
            for r in recs:
                line = json.dumps(r, ensure_ascii=False)
                fh.write(line + "\n")
                if comb:
                    comb.write(line + "\n")
        if a.preview:
            write_preview(Path(a.out_dir) / f.name if a.out_dir else f, recs)
        tot += len(recs)
        print(f"{f}: {len(recs)} chunks from {st['units']} texts (dropped contents pages {st['toc_pages']})", file=sys.stderr)
    if comb:
        comb.close()
    print(f"total {tot} chunks", file=sys.stderr)


if __name__ == "__main__":
    main()
