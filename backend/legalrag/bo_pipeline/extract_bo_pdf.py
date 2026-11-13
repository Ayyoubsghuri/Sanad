#!/usr/bin/env python3
"""
Arabic Bulletin Officiel (BO) PDF extractor  --  no OCR, no regex "glue".

WHY the old version went bad
----------------------------
The text layer of these PDFs is fine, but the fonts' /ToUnicode maps are wrong
(InDesign export of Sakkal Majalla).  Measured on BO_6843_Ar.pdf:
  * Regular CID font : glyph 0003 (space) -> "("      7,945 uses
                       glyph 06B2 (lam)   -> "ج"        594 uses
                       glyph 027E (ى)     -> " "        189 uses
                       glyph 06DC is only a connector piece but -> "ض"
                       7 split-letter glyphs (س ص ض ث) -> U+FFFD
  * Bold CID font    : 38% of glyph uses mapped to the WRONG letter
                       (ا->د, و->م, د->س, س->د, blank->ى, ...)
Regexes cannot repair that reliably.  This script fixes the cause:

  1. Rebuild every Sakkal /ToUnicode from ground truth
       - the font's own cmap (kept in the Sakkal TrueType subset inside the PDF)
       - a verified table of the contextual-alternate glyphs (ALT, below)
     and write the repaired PDF to memory.
  2. Extract characters with their real geometry (pdfplumber).
  3. Rebuild reading order: gutter-aware columns, table cells from ruling lines,
     and proper visual->logical bidi reordering (digit / Latin runs stay LTR).

v2: fonts that carry NO /ToUnicode at all (e.g. BO_7547-bis: every font) used to come out as "(cid:516)".
    They are now decoded from sakkal_labels.json (next to this script): outline-hash -> text, then glyph-id -> text
    per font build.  Rebuild / extend the labels from any PDFs that DO have a ToUnicode:
        python extract_bo_pdf_v2.py --build-labels BO_7546_Ar.pdf BO_7547_Ar.pdf BO_7548_Ar.pdf
Usage:
    python extract_bo_pdf.py BO_6843_Ar.pdf
    python extract_bo_pdf.py BO_6843_Ar.pdf -p 1-5 -f md --report
"""
from __future__ import annotations

import argparse
import io
import json
import re
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import hashlib
import pdfplumber
import pikepdf

try:
    import numpy as np
    import pypdfium2 as pdfium
except ImportError:        # visibility filter is optional
    np = pdfium = None
    print("WARNING: numpy/pypdfium2 missing -> no ink-coverage audit and no hidden-text filter.  pip install numpy pypdfium2", file=sys.stderr)

try:
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("ERROR: the 'fonttools' package is not installed - without it the Arabic glyph repair silently degrades "
             "(wrong/missing letters, 'unverified glyphs').\nInstall it:  pip install fonttools")

# ---------------------------------------------------------------------------
# Verified glyph table (Sakkal Majalla regular+bold share this gid layout;
# Bold's high alternates are shifted by 0x44 and handled in repair()).
# Every entry was checked against the rendered glyph outline.
# ---------------------------------------------------------------------------
ALT = {
    0x1FF:'ئ', 0x201:'ئ', 0x20A:'ب', 0x20B:'ب', 0x20C:'ب', 0x20E:'ب',
    0x216:'ت', 0x218:'ت', 0x21E:'ث', 0x260:'ك', 0x262:'ك', 0x272:'ن',
    0x274:'ن', 0x278:'ه', 0x27A:'ه', 0x27E:'ى', 0x284:'ى', 0x287:'ي',
    0x288:'ي', 0x289:'ي', 0x28B:'ي', 0x28F:'ي', 0x5FF:'م', 0x604:'ب',
    0x605:'ت', 0x607:'ن', 0x608:'ي', 0x61F:'س', 0x620:'س', 0x621:'ث',
    0x637:'ص', 0x638:'ص', 0x639:'ض', 0x63A:'ض', 0x641:'ر', 0x642:'ز',
    0x652:'ت', 0x654:'ن', 0x655:'ي', 0x66D:'ب', 0x66E:'ت', 0x66F:'ث',
    0x670:'ن', 0x688:'ه', 0x68A:'ج', 0x68B:'ج', 0x68C:'ح', 0x68D:'ح',
    0x6A4:'ع', 0x6A5:'ع', 0x6B2:'ل', 0x6B4:'ل', 0x6D7:'ب', 0x6D8:'ت',
    0x6DA:'ن', 0x6DB:'ي', 0x6DC:'\u200b', 0x6F6:'هن', 0x722:'ى', 0x723:'ي',
    0x725:'س', 0x726:'س', 0x727:'ش', 0x728:'ش', 0x735:'ص', 0x736:'ص',
    0x738:'ض', 0x73F:'ع', 0x740:'ع', 0x74D:'ل', 0x74F:'ل', 0x75D:'لم',
    0x768:'ج', 0x76E:'ج', 0x76F:'ح', 0x770:'ح', 0x771:'ح', 0x773:'ح',
    0x775:'خ', 0x778:'خ', 0x8AD:'ف', 0x8AE:'ق', 0x8BC:'ه',
    0x8AB: ' ',            # justified space (Bold gid 0x867)
    # added after checking BO_6838-bis / 6840 / 6842 glyph by glyph:
    0x40B: 'ه', 0x606: 'ث', 0x603: 'ئ', 0x671: 'ي', 0x6A7: 'غ', 0x6C2: 'ه', 0x6D6: 'ئ',
    0x6D9: 'ث',            # added after BO_7472
    0x622: 'ش',            # first half of a split letter (followed by connector 0x6DC)
}
KEEP_TU = {0xB, 0xC, 0xA1, 0xA2}   # mirrored brackets/guillemets: RTL logical form is already right
BOLD_SHIFT_FROM, BOLD_SHIFT = 0x7B4, 0x44
ZW = "\u200b"
LIG = {0xFEF5: "لآ", 0xFEF6: "لآ", 0xFEF7: "لأ", 0xFEF8: "لأ", 0xFEF9: "لإ",
       0xFEFA: "لإ", 0xFEFB: "لا", 0xFEFC: "لا", 0xFDF2: "الله"}

AR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")



# ---------------------------------------------------------------------------
# 0. Label store for fonts that have no ToUnicode (outline hash / glyph id -> text)
# ---------------------------------------------------------------------------
LABELS_FILE = Path(__file__).with_name("sakkal_labels.json")
_LABELS = None


def load_labels() -> dict:
    global _LABELS
    if _LABELS is None:
        try:
            _LABELS = json.loads(LABELS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            sys.exit(f"ERROR: cannot read the glyph table {LABELS_FILE} ({e!r}).\n"
                     f"Put sakkal_labels.json in the SAME folder as extract_bo_pdf.py (copy both from the latest zip). "
                     f"Without it many Arabic glyphs cannot be decoded.")
        print(f"glyph table: {LABELS_FILE} ({len(_LABELS['hash'])} outline hashes, {len(_LABELS['gid'])} glyph ids)", file=sys.stderr)
    return _LABELS


def glyph_hash(t, gid, order):
    """Fingerprint of a glyph outline: identical across subsets / pages / glyph-id layouts of the same font."""
    try:
        g = t["glyf"][order[gid]]
        if g.numberOfContours == 0:
            return None
        c, ends, _ = g.getCoordinates(t["glyf"])
        return hashlib.md5((str(list(map(tuple, c))) + str(list(ends))).encode()).hexdigest()
    except Exception:
        return None


def font_family(f) -> str:
    return str(f.get("/BaseFont", "")).lstrip("/").split("+")[-1]


def type0_ttf(f):
    try:
        ff = f.DescendantFonts[0].FontDescriptor.get("/FontFile2")
        return TTFont(io.BytesIO(ff.read_bytes())) if ff is not None and TTFont is not None else None
    except Exception:
        return None


def build_labels(pdf_paths, out=LABELS_FILE):
    """Collect gid->text and outline-hash->text from PDFs whose fonts DO have a ToUnicode."""
    from collections import Counter
    H, G = defaultdict(lambda: defaultdict(Counter)), defaultdict(lambda: defaultdict(Counter))
    for path in pdf_paths:
        pk = pikepdf.open(path)
        repair(pk)                                           # fixes the Sakkal maps first
        for f in all_fonts(pk).values():
            if str(f.get("/Subtype")) != "/Type0" or "/ToUnicode" not in f:
                continue
            t = type0_ttf(f)
            if t is None:
                continue
            fam, order, n = font_family(f), t.getGlyphOrder(), len(t.getGlyphOrder())
            for gid, txt in parse_tounicode(f).items():
                if not txt or "\ufffd" in txt or gid <= 0 or gid >= n:
                    continue
                G[f"{fam}:{n}"][gid][txt] += 1
                h = glyph_hash(t, gid, order)
                if h:
                    H[fam][h][txt] += 1
    top = lambda c: c.most_common(1)[0][0]
    lab = {"hash": {k: {h: top(c) for h, c in d.items()} for k, d in H.items()},
           "gid": {k: {str(g): top(c) for g, c in d.items()} for k, d in G.items()}}
    Path(out).write_text(json.dumps(lab, ensure_ascii=False), encoding="utf-8")
    print(f"labels -> {out}: " + ", ".join(f"{k} {len(v)} outlines" for k, v in lab["hash"].items()), file=sys.stderr)


# glyphs identified by eye (rendered outline) that no reference PDF contains; key = "BaseFont:numGlyphs"
MANUAL = {
    "SakkalMajalla:3244": {170: "\u201c", 171: "\u201d", 540: "ث", 1888: "ه", 1898: "ج",
                           515: "ئ", 1381: "\u064b", 1619: "ث", 1780: "هت", 1783: "هي", 1825: "ئ",
                           1858: "غ", 1906: "ح", 2270: "لله", 3222: "ج"},
    "SakkalMajalla-Bold:3244": {1847: "ض"},
    "SakkalMajalla-Bold:3016": {1644: "ئ", 2154: "ق", 1894: "ج"},
    "ArialMT:4651": {402: "\u25aa"},
    "ArialMT:4548": {751: "ء"}, "Arial-BoldMT:4548": {751: "ء"},
}


FIXES_FILE = Path(__file__).with_name("glyph_fixes.json")
_FIXDATA = None


def load_fixdata() -> dict:
    """glyph_fixes.json (optional), built by learn_glyphs.py:
         "hash":     {outline-hash: placeholder}   a letter the font's ToUnicode leaves as U+FFFD, identified by its outline
                     (identical in every subset of the same font, in every page and every bulletin that uses that font)
         "clusters": {run of placeholders: text}   what a run of such glyphs spells (a glyph is often half a letter pair)
         "words":    {wrong: right}                spaces left inside words by displaced dots / fixed misreadings
         "groups":   {"glyph count:gid": placeholder}   bookkeeping for learn_glyphs.py"""
    global _FIXDATA
    if _FIXDATA is None:
        try:
            _FIXDATA = json.loads(FIXES_FILE.read_text(encoding="utf-8"))
        except Exception:
            _FIXDATA = {}
        for k in ("hash", "clusters", "words", "subs", "groups"):
            _FIXDATA.setdefault(k, {})
        extra = os.environ.get("BO_FFFD_PUA")                  # learning mode: keep placeholders in the text (see learn_glyphs.py)
        if extra:
            _FIXDATA["keep_placeholders"] = True
            try:                                               # a value that is a flat hash->placeholder file is merged in (old workflow)
                m = json.loads(Path(extra).read_text(encoding="utf-8"))
                if m and "hash" not in m:
                    _FIXDATA["hash"] = {**_FIXDATA["hash"], **m}
            except Exception:
                pass
    return _FIXDATA


def load_fixes() -> dict:
    return load_fixdata()["hash"]


DOT_BEFORE = "\u0646\u062a\u0628"      # ن ت ب: a dot that some fonts store as a separate letter just before the glyph it belongs to
BODY_AFTER = "\u0633\u0635\u0636\u0634\u0637\u0638"  # س ص ض ش ط ظ: the tooth glyph's stand-in body letter, wrong whatever it is


def repair_text(s: str) -> str:
    """After extraction: placeholders -> the letters they stand for, run by run (a stray dot letter right before the run and
    a stand-in body letter right after it can be part of the key; "*" in a key = any body letter), then the word fixes.
    A run nobody has labelled yet becomes U+FFFD again, so check_chunks.py still reports it."""
    fd = load_fixdata()
    if fd.get("keep_placeholders") or not fd["hash"]:
        return s
    ph = "".join(sorted(set(fd["hash"].values())))
    rx = re.compile(f"([{DOT_BEFORE}]?)([{ph}]+)([{BODY_AFTER}]?)")
    cl = fd["clusters"]

    def one(m):
        pre, run, suf = m.groups()
        tries = []
        if pre and suf:
            tries += [(pre + run + suf, 1, 1), (pre + run + "*", 1, 1)]
        if suf:
            tries += [(run + suf, 0, 1), (run + "*", 0, 1)]
        if pre:
            tries += [(pre + run, 1, 0)]
        tries += [(run, 0, 0)]
        for key, eat_pre, eat_suf in tries:                    # what the key does not use stays in the text
            if key in cl:
                return ("" if eat_pre else pre) + cl[key] + ("" if eat_suf else suf)
        return pre + "\ufffd" * len(run) + suf
    s = rx.sub(one, s)
    for wrong, right in sorted(fd["subs"].items(), key=lambda kv: -len(kv[0])):
        s = s.replace(wrong, right)
    for wrong, right in sorted(fd["words"].items(), key=lambda kv: -len(kv[0])):
        s = re.sub("(?<![\u0621-\u064A])" + re.escape(wrong), right, s)
    return s


def _blank_glyph(t, name) -> bool:
    try:
        return t["glyf"][name].numberOfContours == 0
    except Exception:
        return False


def fix_fffd_glyphs(pdf, fonts, stats):
    """Type0 fonts whose ToUnicode says U+FFFD for some glyphs: look the glyph outline up in glyph_fixes.json."""
    fx = load_fixes()
    stats.setdefault("fffd_fixed", 0); stats.setdefault("fffd_left", 0)
    for f in fonts.values():
        if str(f.get("/Subtype")) != "/Type0" or "/ToUnicode" not in f or TTFont is None:
            continue
        old = parse_tounicode(f)
        bad = [g for g, v in old.items() if "\ufffd" in v]
        if not bad:
            continue
        t = type0_ttf(f)
        if t is None:
            stats["fffd_left"] += len(bad); continue
        order, new, n = t.getGlyphOrder(), dict(old), 0
        for g in bad:
            h = glyph_hash(t, g, order) if 0 < g < len(order) else None
            if h and h in fx:
                new[g] = fx[h]; n += 1
            elif g == 0 or (h is None and 0 < g < len(order) and _blank_glyph(t, order[g])):
                new[g] = ""; n += 1                              # .notdef (glyph 0) or an outline-less glyph: it stands for no letter
        stats["fffd_fixed"] += n; stats["fffd_left"] += len(bad) - n
        if n:
            f.ToUnicode = pdf.make_stream(make_cmap(new))


def label_font(f, stats):
    """ToUnicode for a Type0 font that has none: outline hash, then glyph id (same font build), then ALT."""
    t = type0_ttf(f)
    if t is None:
        return None
    L = load_labels()
    fam, order = font_family(f), t.getGlyphOrder()
    n = len(order)
    H, G = L["hash"].get(fam, {}), dict(L["gid"].get(f"{fam}:{n}", {}))
    G.update({str(k): v for k, v in MANUAL.get(f"{fam}:{n}", {}).items()})
    sak = "Sakkal" in fam
    new = {}
    for gid in range(1, n):
        h = glyph_hash(t, gid, order)
        val = H.get(h) if h else None
        if val is None:
            val = G.get(str(gid))
        if val is None and sak and n == 3244 and gid in ALT:
            val = ALT[gid]
        if val is None and "SegoeMDL2" in fam and gid == 414:
            val = "\u2713"                                          # check mark icon
        if val is None and "Arial" in fam and 896 <= gid <= 1020:
            # Arial's Arabic block = presentation forms U+FE80..FEFC in order (verified glyph by glyph)
            val = unicodedata.normalize("NFKC", chr(0xFE80 + gid - 896))
        if val is None and "Calibri" in fam:
            if 1004 <= gid <= 1013: val = str(gid - 1004)          # digits
            elif 964 <= gid <= 973: val = str(gid - 964)           # alternate digit set
            elif gid == 853: val = ","
            elif gid == 856: val = "."
        if val is None and 3 <= gid <= 97 and re.search("Arial|Times|Calibri|Sakkal", fam):
            val = chr(gid + 29)                              # MS TrueType standard glyph order (3 <= gid <= 97 only)
        if val is None:
            if h:
                stats["unverified"][fam].add(gid)
            continue
        new[gid] = val
    return new

# ---------------------------------------------------------------------------
# 1. Font repair
# ---------------------------------------------------------------------------
def parse_tounicode(font) -> dict[int, str]:
    out: dict[int, str] = {}
    if "/ToUnicode" not in font:
        return out
    tu = font.ToUnicode.read_bytes().decode("latin-1")
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", tu, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", blk):
            out[int(a, 16)] = bytes.fromhex(b).decode("utf-16-be", "replace")
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", tu, re.S):
        for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            a, b = int(a, 16), int(b, 16)
            if b < a or b - a > 0xFFFF:
                continue                                  # malformed range
            if len(c) % 4:
                c = c.zfill(len(c) + 4 - len(c) % 4)
            try:
                d = bytes.fromhex(c).decode("utf-16-be", "replace")      # full destination (surrogate pairs decode here)
            except Exception:
                continue
            if not d:
                continue
            head, last = d[:-1], ord(d[-1])
            for i in range(a, b + 1):                     # a multi-character destination: only its last character counts up
                u = last + i - a
                out[i] = head + (chr(u) if u < 0x110000 and not 0xD800 <= u < 0xE000 else "\ufffd")
    return out


def make_cmap(mapping: dict[int, str], width: int = 4) -> bytes:
    L = ["/CIDInit /ProcSet findresource begin 12 dict begin begincmap",
         "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
         "/CMapName /Adobe-Identity-UCS def /CMapType 2 def",
         f"1 begincodespacerange <{'0' * width}> <{'F' * width}> endcodespacerange"]
    items = sorted(mapping.items())
    for i in range(0, len(items), 100):
        ch = items[i:i + 100]
        L.append(f"{len(ch)} beginbfchar")
        for c, s in ch:
            L.append(f"<{c:0{width}X}> <{s.encode('utf-16-be').hex().upper()}>")
        L.append("endbfchar")
    L.append("endcmap CMapName currentdict /CMap defineresource pop end end")
    return "\n".join(L).encode()


def all_fonts(pdf) -> dict:
    fonts, seen = {}, set()

    def walk(res):
        for _, f in (res.get("/Font") or {}).items():
            fonts[f.objgen] = f
        for _, xo in (res.get("/XObject") or {}).items():
            if xo.get("/Subtype") == "/Form" and xo.objgen not in seen:
                seen.add(xo.objgen)
                walk(xo.get("/Resources") or res)

    for p in pdf.pages:
        if "/Resources" in p:
            walk(p.Resources)
    return fonts


def sakkal_cmap_truth(fonts) -> dict[int, str]:
    """gid -> text from the Sakkal TrueType subset that still carries a full cmap."""
    if TTFont is None:
        return {}
    for f in fonts.values():
        if "Sakkal" in str(f.get("/BaseFont", "")) and str(f.get("/Subtype")) == "/TrueType":
            fd = f.get("/FontDescriptor")
            ff = fd.get("/FontFile2") if fd is not None else None
            if ff is None:
                continue
            t = TTFont(io.BytesIO(ff.read_bytes()))
            if "cmap" not in t:
                continue
            truth: dict[int, str] = {}
            for u, gn in t.getBestCmap().items():
                gid = t.getGlyphID(gn)
                if u in LIG:
                    s = LIG[u]
                elif 0xFB50 <= u <= 0xFEFF:
                    s = unicodedata.normalize("NFKC", chr(u))
                elif 0x0600 <= u <= 0x06FF or u == 0x20:
                    s = chr(u)
                else:
                    continue
                if s == "ھ":
                    s = "ه"
                if gid not in truth or 0x600 <= u <= 0x6FF:
                    truth.setdefault(gid, s)
            truth[3] = " "
            return truth
    return {}


def repair(pdf) -> dict:
    fonts = all_fonts(pdf)
    cm = sakkal_cmap_truth(fonts)
    stats = {"fonts_fixed": 0, "codes_changed": 0, "unverified": defaultdict(set)}
    for key, f in fonts.items():
        base = str(f.get("/BaseFont", ""))
        if str(f.get("/Subtype")) == "/Type0" and "/ToUnicode" not in f:
            new = label_font(f, stats)                       # v2: no ToUnicode at all
            if new:
                f.ToUnicode = pdf.make_stream(make_cmap(new))
                stats["fonts_fixed"] += 1; stats["codes_changed"] += len(new)
            continue
        if str(f.get("/Subtype")) == "/TrueType" and "WinAnsi" in str(f.get("/Encoding")):
            # simple fonts: ToUnicode must equal the encoding (Sakkal Bold digits are scrambled).
            old = parse_tounicode(f) or {c: "?" for c in range(32, 256)}    # v2: no ToUnicode -> use the encoding
            new = dict(old)
            for code in old:
                if code in (0x28, 0x29, 0xAB, 0xBB, 0):
                    if old[code] == "?":                    # v2: no original map -> plain encoding char
                        new[code] = bytes([code]).decode("cp1252", "replace")
                    continue            # mirrored brackets: RTL logical form already right
                ch = bytes([code]).decode("cp1252", "replace")
                if new[code] != ch:
                    new[code] = ch; stats["codes_changed"] += 1
            f.ToUnicode = pdf.make_stream(make_cmap(new, 2))
            continue
        if "Sakkal" not in base and str(f.get("/Subtype")) in ("/Type0", "/TrueType") and TTFont is not None:
            old = parse_tounicode(f)
            blanks = [g for g, v in old.items() if v != "" and v.strip() == ""]
            if blanks:
                try:
                    simple = str(f.get("/Subtype")) == "/TrueType"
                    d = f if simple else f.DescendantFonts[0]
                    t = TTFont(io.BytesIO(d.FontDescriptor.FontFile2.read_bytes()))
                    order = t.getGlyphOrder(); new = dict(old); n = 0

                    def gid_of(code):
                        if not simple:
                            return code
                        for tab in t["cmap"].tables if "cmap" in t else []:
                            if (tab.platformID, tab.platEncID) == (3, 0):
                                for off in (0xF000, 0):
                                    if off + code in tab.cmap:
                                        return t.getGlyphID(tab.cmap[off + code])
                            if (tab.platformID, tab.platEncID) == (1, 0) and code in tab.cmap:
                                return t.getGlyphID(tab.cmap[code])
                        return None

                    for g in blanks:
                        gi = gid_of(g)
                        if gi is None or gi >= len(order) or "glyf" not in t:
                            continue
                        gl = t["glyf"][order[gi]]
                        if gl.numberOfContours > 0 and hasattr(gl, "coordinates") and len(gl.coordinates) > 4:
                            xs = [p[0] for p in gl.coordinates]; ys = [p[1] for p in gl.coordinates]
                            w, h = max(xs) - min(xs), max(ys) - min(ys)
                            if h > 1.6 * w and h > 0:      # tall narrow stroke: a bracket whose map says "space"
                                new[g] = "(" if sum(xs) / len(xs) < (max(xs) + min(xs)) / 2 else ")"
                                n += 1
                    if n:
                        f.ToUnicode = pdf.make_stream(make_cmap(new, 2 if simple else 4)); stats["codes_changed"] += n
                except Exception:
                    pass
        if "Sakkal" not in base or str(f.get("/Subtype")) != "/Type0":
            continue
        bold = "Bold" in base
        legacy = True                       # old 2261-glyph Sakkal: scrambled Bold maps + shifted Bold alternates
        try:
            ff = f.DescendantFonts[0].FontDescriptor.FontFile2
            legacy = TTFont(io.BytesIO(ff.read_bytes()), lazy=True)["maxp"].numGlyphs == 2261
        except Exception:
            pass
        old = parse_tounicode(f)
        new = dict(old)
        for gid in set(old) | set(ALT) | set(cm):
            if gid in (0, 0xFFFF):
                continue
            g2 = gid + BOLD_SHIFT if (legacy and bold and gid >= BOLD_SHIFT_FROM) else gid
            if gid in KEEP_TU and gid in old:
                continue
            if g2 in ALT:
                val = ALT[g2]
            elif gid in cm and not (legacy and bold and gid >= BOLD_SHIFT_FROM):
                val = cm[gid]
            elif gid in old:
                val = old[gid]
                if val in ("\ufffd", "") or (legacy and bold and AR.search(val)):
                    stats["unverified"][base].add(gid)
            else:
                continue
            if new.get(gid) != val:
                stats["codes_changed"] += 1
            new[gid] = val
        f.ToUnicode = pdf.make_stream(make_cmap(new))
        stats["fonts_fixed"] += 1
    fix_fffd_glyphs(pdf, fonts, stats)
    return stats



# ---------------------------------------------------------------------------
# 1b. Clipped (never visible) text
# ---------------------------------------------------------------------------
def _mul(a, b):
    return (a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5])


_PAINT = {"n", "f", "F", "f*", "B", "B*", "b", "b*", "S", "s"}


def _strip_stream(pdf, obj, res, ctm, clip, seen, stats):
    """Blank text-show operators whose origin lies outside the active rectangular clip.
    Such text is clipped away when rendered, but text extractors still return it."""
    ops = list(pikepdf.parse_content_stream(obj))
    stack = []
    path = []                        # device-space bboxes of rect(s) in the current path
    pending = False
    tm = tlm = (1, 0, 0, 1, 0, 0)
    leading = 0.0
    changed = False
    out = []
    for operands, op in ops:
        o = str(op)
        if o == "q":
            stack.append((ctm, clip))
        elif o == "Q":
            if stack:
                ctm, clip = stack.pop()
        elif o == "cm":
            ctm = _mul(tuple(float(x) for x in operands), ctm)
        elif o == "re":
            x, y, w, h = (float(v) for v in operands)
            pts = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
            dev = [(px * ctm[0] + py * ctm[2] + ctm[4], px * ctm[1] + py * ctm[3] + ctm[5]) for px, py in pts]
            path.append((min(p[0] for p in dev), min(p[1] for p in dev), max(p[0] for p in dev), max(p[1] for p in dev)))
        elif o in ("W", "W*"):
            pending = True
        elif o in _PAINT:
            if pending and path:
                bb = (min(p[0] for p in path), min(p[1] for p in path), max(p[2] for p in path), max(p[3] for p in path))
                clip = bb if clip is None else (max(clip[0], bb[0]), max(clip[1], bb[1]), min(clip[2], bb[2]), min(clip[3], bb[3]))
            path, pending = [], False
        elif o == "BT":
            tm = tlm = (1, 0, 0, 1, 0, 0)
        elif o == "Tm":
            tm = tlm = tuple(float(x) for x in operands)
        elif o in ("Td", "TD"):
            tx, ty = float(operands[0]), float(operands[1])
            if o == "TD":
                leading = -ty
            tlm = _mul((1, 0, 0, 1, tx, ty), tlm); tm = tlm
        elif o == "TL":
            leading = float(operands[0])
        elif o in ("T*", "'", '"'):
            tlm = _mul((1, 0, 0, 1, 0, -leading), tlm); tm = tlm
        if o in ("Tj", "TJ", "'", '"') and clip is not None:
            dm = _mul(tm, ctm)
            x, y = dm[4], dm[5]
            if not (clip[0] - 3 <= x <= clip[2] + 3 and clip[1] - 4 <= y <= clip[3] + 4):
                if o == "TJ":
                    operands = [pikepdf.Array([])]
                else:
                    operands = list(operands[:-1]) + [pikepdf.String(b"")]
                changed = True; stats["blanked"] += 1
        if o == "Do":
            xo = (res.get("/XObject") or {}).get(str(operands[0]))
            if xo is not None and xo.get("/Subtype") == "/Form" and xo.objgen not in seen:
                seen.add(xo.objgen)
                fm = tuple(float(x) for x in xo.get("/Matrix", [1, 0, 0, 1, 0, 0]))
                _strip_stream(pdf, xo, xo.get("/Resources", res), _mul(fm, ctm), clip, seen, stats)
        out.append((operands, op))
    if changed:
        data = pikepdf.unparse_content_stream(out)
        if isinstance(obj, pikepdf.Page) or "/Type" in obj and str(obj.get("/Type")) == "/Page":
            obj.Contents = pdf.make_stream(data)
        else:
            obj.write(data)


def strip_clipped_text(pdf) -> int:
    stats = {"blanked": 0}
    for page in pdf.pages:
        try:
            _strip_stream(pdf, page, page.Resources, (1, 0, 0, 1, 0, 0), None, set(), stats)
        except Exception:                    # never let a odd page break extraction
            continue
    return stats["blanked"]

# ---------------------------------------------------------------------------
# 2. Bidi: visual (left->right) chars  ->  logical text
# ---------------------------------------------------------------------------
def cls(t: str) -> str:
    if AR.search(t):
        return "R"
    if re.search(r"[0-9\u0660-\u0669]", t):
        return "N"
    if re.search(r"[A-Za-z\u00C0-\u024F]", t):
        return "L"
    if t.strip() == "":
        return "S"
    return "P"


NUM_JOIN = set("./,:-+%")


def visual_to_logical(chars: list[dict], space_gap: float = 0.28) -> str:
    """chars: dicts with text,x0,x1,size.  Returns logical text of ONE line."""
    cs = [c for c in chars if c["text"] != ""]
    if not any(c["text"] != ZW for c in cs):
        return ""
    marks = [c for c in cs if c["text"] and all(unicodedata.category(ch) == "Mn" for ch in c["text"])]
    if marks:
        cs = [c for c in cs if c not in marks]
        bases = [dict(c) for c in cs if c["text"].strip() and c["text"] != ZW]
        extra = defaultdict(list)
        for m in marks:
            mc = (m["x0"] + m["x1"]) / 2
            best = min(bases, key=lambda b: abs((b["x0"] + b["x1"]) / 2 - mc), default=None)
            if best is not None and abs((best["x0"] + best["x1"]) / 2 - mc) < 14:
                extra[id(best)].append(m["text"])
        lookup = {(b["x0"], b["x1"], b["top"]): b for b in bases}
        cs = [lookup.get((c["x0"], c["x1"], c["top"]), c) if c["text"].strip() and c["text"] != ZW else c for c in cs]
        for c in cs:
            ex = extra.get(id(c))
            if ex:
                c["text"] = c["text"] + "".join(ex)
    vis = [c for c in cs if not c["text"].isspace()]
    cs = [c for c in cs if not c["text"].isspace() or (
        c["x1"] - c["x0"] > 0.5 and not any(abs(v["x0"] - c["x0"]) < 0.4 and abs(v["x1"] - c["x1"]) < 0.4 for v in vis))]
    cs.sort(key=lambda c: (c["x0"] + c["x1"]) / 2)
    # insert gap-based spaces (explicit space glyphs are the norm in BO)
    seq: list[tuple[str, str]] = []
    prev = None
    for c in cs:
        t = c["text"]
        if prev is not None and not t.isspace() and not prev["text"].isspace():
            if c["x0"] - prev["x1"] > space_gap * max(c.get("size", 10), 6):
                seq.append((" ", "S"))
        if t != ZW:                            # connector pieces bridge gaps but emit nothing
            seq.append((t, cls(t)))
        prev = c
    n_r = sum(1 for _, k in seq if k == "R")
    n_l = sum(1 for _, k in seq if k == "L")
    rtl = n_r >= n_l and n_r + n_l > 0 or (n_r == 0 and n_l == 0)
    # which chars belong to an "other-direction" run
    mem = [False] * len(seq)
    inner = "LN" if rtl else "R"
    for i, (t, k) in enumerate(seq):
        if k in inner:
            mem[i] = True
    for i, (t, k) in enumerate(seq):           # neutrals sandwiched between members
        if mem[i] or k not in ("S", "P"):
            continue
        j = i - 1
        while j >= 0 and seq[j][1] in ("S", "P") and not mem[j]:
            j -= 1
        m = i + 1
        while m < len(seq) and seq[m][1] in ("S", "P") and not mem[m]:
            m += 1
        if j < 0 or m >= len(seq) or not (mem[j] and mem[m]):
            continue
        span = seq[j + 1:m]
        if rtl:
            a, b = seq[j][1], seq[m][1]
            ok = all(s[0] in NUM_JOIN for s in span) and a == "N" and b == "N"
            if not ok and a == "N" and b == "N" and len(span) == 1 and span[0][0] == " ":
                lft = 0
                q = j
                while q >= 0 and seq[q][1] == "N" and seq[q][0].isdigit():
                    lft += 1; q -= 1
                rgt = 0
                q = m
                while q < len(seq) and seq[q][1] == "N" and seq[q][0].isdigit():
                    rgt += 1; q += 1
                ok = rgt == 3 and 1 <= lft <= 3
            ok = ok or (a == "L" and b == "L" and all(s[0] in " .,'-/&" for s in span))
        else:
            ok = True
        if ok:
            for q in range(j + 1, m):
                mem[q] = True
    if rtl:                                    # % / currency touching digits
        for i, (t, k) in enumerate(seq):
            if t in "%" and not mem[i] and ((i > 0 and mem[i - 1] and seq[i - 1][1] == "N") or
                                             (i + 1 < len(seq) and mem[i + 1] and seq[i + 1][1] == "N")):
                mem[i] = True
    units: list[list[str]] = []
    run: list[str] = []
    for (t, k), m in zip(seq, mem):
        if m:
            run.append(t)
        else:
            if run:
                units.append(run); run = []
            units.append([t])
    if run:
        units.append(run)
    if rtl:
        out = "".join("".join(u) for u in reversed(units))
    else:
        out = "".join("".join(reversed(u)) if (len(u) > 0 and AR.search("".join(u))) else "".join(u) for u in units)
    return fix_brackets(out)


def fix_brackets(s: str) -> str:
    o, c = s.count("("), s.count(")")
    if o != c and (o + c) % 2 == 0:            # unbalanced: re-pair alternately in logical order
        k = 0
        def alt(m):
            nonlocal k
            k += 1
            return "(" if k % 2 else ")"
        return re.sub(r"[()]", alt, s)
    depth = 0; bad = False
    for ch in s:
        if ch in "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                bad = True
    if bad and s.count("(") == s.count(")"):
        s = s.translate(str.maketrans("()", ")("))
    return s


def clean(s: str, keep_leaders: bool = False) -> str:
    s = re.sub(r"[\uFB50-\uFDFF\uFE70-\uFEFF]+", lambda m: unicodedata.normalize("NFKC", m.group(0)), s)
    s = s.replace(ZW, "").replace("\u0640", "").replace("\u06d5", "\u0647")   # ە -> ه
    s = re.sub(r"[\uf0b7\uf0a7\uf0d8\uf076\uf0fc]", "•", s)      # Symbol/Wingdings bullets
    s = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", s)
    if not keep_leaders:
        s = re.sub(r"(?:\.\s*){4,}", " … ", s)
    return re.sub(r"[ \u00a0]+", " ", s).strip()


# ---------------------------------------------------------------------------
# 3. Page layout
# ---------------------------------------------------------------------------
def cluster_rows(chars: list[dict]) -> list[list[dict]]:
    """Group glyphs into text lines. Tolerance uses the SMALLER glyph size so large
    headings never swallow nearby small text (scaled-down forms)."""
    rows: list[list] = []                       # [cy, chars, min_size]
    for c in sorted(chars, key=lambda c: (c["top"] + c["bottom"]) / 2):
        cy = (c["top"] + c["bottom"]) / 2
        sz = max(c["size"], 4)
        if rows and abs(cy - rows[-1][0]) <= 0.45 * min(sz, rows[-1][2]):
            r = rows[-1]; r[1].append(c); r[2] = min(r[2], sz)
            r[0] = sum((x["top"] + x["bottom"]) / 2 for x in r[1]) / len(r[1])
        else:
            rows.append([cy, [c], sz])
    return [r[1] for r in rows]


GUTTER_TOL = 0.35


def column_zones(page, W):
    """Vertical rules near the page middle (the line printed between the two columns).  Returns [(x, top, bottom)];
    the rule may cover only part of the page (columns above a figure, full-width text elsewhere)."""
    segs = []
    for o in list(page.lines) + list(page.rects):
        if abs(o["x1"] - o["x0"]) < 3 and o["bottom"] - o["top"] > 60 and 0.38 * W < (o["x0"] + o["x1"]) / 2 < 0.62 * W:
            segs.append(((o["x0"] + o["x1"]) / 2, o["top"], o["bottom"]))
    if not segs:
        return []
    segs.sort(key=lambda z: (round(z[0]), z[1]))
    out = []
    for x, t, b in segs:
        if out and abs(out[-1][0] - x) < 3 and t <= out[-1][2] + 6:
            out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], b))
        else:
            out.append((x, t, b))
    return [z for z in out if z[2] - z[1] > 60]


def find_gutter(rows, W):
    n = int(W) + 1
    cov = [0] * n
    for r in rows:
        spans = set()
        for c in r:
            if c["text"].strip():
                spans.update(range(max(int(c["x0"]), 0), min(int(c["x1"]) + 1, n)))
        for x in spans:
            cov[x] += 1
    mx = max(cov) if cov else 0
    if mx < 8:
        return None
    lo, hi = int(W * 0.38), int(W * 0.62)
    best, cur = None, None
    for x in range(lo, hi):
        if cov[x] <= GUTTER_TOL * mx:
            cur = (cur[0], x) if cur else (x, x)
            if best is None or cur[1] - cur[0] > best[1] - best[0]:
                best = cur
        else:
            cur = None
    if best and best[1] - best[0] >= 5:
        return best[0], best[1] + 1
    return None


def is_bold(c):
    return "Bold" in c.get("fontname", "")


def line_item(chars, kind="line"):
    text = clean(visual_to_logical(chars))
    if not text:
        return None
    x0 = min(c["x0"] for c in chars); x1 = max(c["x1"] for c in chars)
    top = min(c["top"] for c in chars); bot = max(c["bottom"] for c in chars)
    vis = [c for c in chars if c["text"].strip()]
    return {"type": kind, "text": text, "x0": x0, "x1": x1, "top": top, "bottom": bot,
            "size": round(sum(c["size"] for c in vis) / len(vis), 1),
            "bold": sum(is_bold(c) for c in vis) / len(vis) >= 0.8}


def _edges(vals, tol):
    """Cluster x positions; chained values within tol become one edge."""
    vals = sorted(vals); groups = [[vals[0]]]
    for v in vals[1:]:
        (groups[-1].append(v) if v - groups[-1][-1] <= tol else groups.append([v]))
    return [sum(g) / len(g) for g in groups]


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def f(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]; a = self.p[a]
        return a

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


def _cell_text(chs):
    lines = [l for l in (line_item(r) for r in cluster_rows(chs)) if l]
    lines.sort(key=lambda l: l["top"])
    bold = bool(lines) and sum(l["bold"] for l in lines) / len(lines) >= 0.7
    return [l["text"] for l in lines], bold


def build_table(page, tb, chars, sliver_w=9.0, sliver_h=6.0, row_keep=0.5):
    """Ruled table -> exact structure.
    * cells come from the ruling lines; thin EMPTY border strips (drawn as rectangles) are collapsed into the
      neighbouring edge, so they never become columns / rows;
    * row spans / column spans are exact (RTL: column 0 = rightmost);
    * a horizontal edge that is only present in some columns (a wrapped cell split by a stray line) is not a
      row boundary: the pieces are merged;
    * every glyph is assigned to exactly one cell (smallest containing cell); glyphs inside the table box that
      belong to no cell are returned as orphans, never dropped.
    Returns (struct, consumed_char_ids, orphan_chars) or None."""
    cells = [tuple(c) for c in tb.cells]
    if len(cells) < 2:
        return None
    # --- edge lattice (rounding noise only), then collapse empty slivers
    rx = _edges([v for c in cells for v in (c[0], c[2])], 1.0)
    ry = _edges([v for c in cells for v in (c[1], c[3])], 1.0)
    ix = lambda v: min(range(len(rx)), key=lambda k: abs(rx[k] - v))
    iy = lambda v: min(range(len(ry)), key=lambda k: abs(ry[k] - v))
    mid = lambda c: ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)
    inside = lambda c, ch: c[0] - 1 <= (ch["x0"] + ch["x1"]) / 2 <= c[2] + 1 and c[1] - 1 <= (ch["top"] + ch["bottom"]) / 2 <= c[3] + 1
    gl = [c for c in chars if c["text"].strip()]
    ufx, ufy = _UF(len(rx)), _UF(len(ry))
    for c in cells:
        w, h = c[2] - c[0], c[3] - c[1]
        if (w < sliver_w or h < sliver_h) and not any(inside(c, ch) for ch in gl):
            if w < sliver_w:
                ufx.u(ix(c[0]), ix(c[2]))
            if h < sliver_h:
                ufy.u(iy(c[1]), iy(c[3]))
    cx = sorted({ufx.f(k) for k in range(len(rx))}); cy = sorted({ufy.f(k) for k in range(len(ry))})
    X = {k: cx.index(ufx.f(k)) for k in range(len(rx))}; Y = {k: cy.index(ufy.f(k)) for k in range(len(ry))}
    xpos = [sum(rx[k] for k in range(len(rx)) if X[k] == n) / sum(1 for k in range(len(rx)) if X[k] == n) for n in range(len(cx))]
    ypos = [sum(ry[k] for k in range(len(ry)) if Y[k] == n) / sum(1 for k in range(len(ry)) if Y[k] == n) for n in range(len(cy))]
    recs, seen = [], set()
    for c in cells:
        x0, x1, y0, y1 = X[ix(c[0])], X[ix(c[2])], Y[iy(c[1])], Y[iy(c[3])]
        if x1 <= x0 or y1 <= y0 or (x0, x1, y0, y1) in seen:
            continue
        seen.add((x0, x1, y0, y1))
        recs.append({"x0": x0, "x1": x1, "y0": y0, "y1": y1, "chars": []})
    # a cell drawn twice (a small one nested inside a bigger one) is a drawing artefact: keep the bigger
    recs = [r for r in recs if not any(o is not r and o["x0"] <= r["x0"] and r["x1"] <= o["x1"] and o["y0"] <= r["y0"] and r["y1"] <= o["y1"]
                                       for o in recs)]
    if not recs:
        return None
    ncol, nrow = len(xpos) - 1, len(ypos) - 1
    # --- glyph -> cell (smallest containing cell wins)
    import bisect
    slot = {}
    for k, r in sorted(enumerate(recs), key=lambda kr: -((kr[1]["x1"] - kr[1]["x0"]) * (kr[1]["y1"] - kr[1]["y0"]))):
        for yy in range(r["y0"], r["y1"]):
            for xx in range(r["x0"], r["x1"]):
                slot[(yy, xx)] = k
    tx0, ty0, tx1, ty1 = xpos[0], ypos[0], xpos[-1], ypos[-1]
    orphans, consumed = [], set()
    for ch in chars:
        cxm, cym = (ch["x0"] + ch["x1"]) / 2, (ch["top"] + ch["bottom"]) / 2
        if not (tx0 - 1 <= cxm <= tx1 + 1 and ty0 - 1 <= cym <= ty1 + 1):
            continue
        xx = min(max(bisect.bisect_right(xpos, cxm) - 1, 0), ncol - 1)
        yy = min(max(bisect.bisect_right(ypos, cym) - 1, 0), nrow - 1)
        k = slot.get((yy, xx))
        if k is None:
            orphans.append(ch)
        else:
            recs[k]["chars"].append(ch); consumed.add(id(ch))
    # --- horizontal edges present in only some columns are not row boundaries: merge the pieces
    total_w = tx1 - tx0
    changed = True
    while changed:
        changed = False
        for j in range(1, nrow):
            ends = [r for r in recs if r["y1"] == j]; starts = [r for r in recs if r["y0"] == j]
            if not ends or not starts:
                continue
            cover = sum(xpos[r["x1"]] - xpos[r["x0"]] for r in ends)
            if cover >= row_keep * total_w:
                continue
            pair = []
            for a in ends:
                b = next((r for r in starts if r["x0"] == a["x0"] and r["x1"] == a["x1"]), None)
                if b is None:
                    pair = None; break
                pair.append((a, b))
            if not pair:
                continue
            for a, b in pair:
                a["chars"] += b["chars"]; a["y1"] = b["y1"]; recs.remove(b)
            changed = True
            break
    # --- text, bold
    out = []
    for r in recs:
        lines, bold = _cell_text(r["chars"])
        out.append({"r": r["y0"], "c": ncol - r["x1"], "rowspan": r["y1"] - r["y0"], "colspan": r["x1"] - r["x0"],
                    "text": " ".join(lines).replace("|", "/"), "lines": lines, "bold": bold})
    # --- compact rows/cols no cell starts or ends at (after merges)
    used_r = sorted({k for c in out for k in (c["r"], c["r"] + c["rowspan"])})
    used_c = sorted({k for c in out for k in (c["c"], c["c"] + c["colspan"])})
    rmap = {v: n for n, v in enumerate(used_r)}; cmap = {v: n for n, v in enumerate(used_c)}
    for c in out:
        r0, r1, c0, c1 = c["r"], c["r"] + c["rowspan"], c["c"], c["c"] + c["colspan"]
        c["r"], c["rowspan"], c["c"], c["colspan"] = rmap[r0], rmap[r1] - rmap[r0], cmap[c0], cmap[c1] - cmap[c0]
    R, C = len(used_r) - 1, len(used_c) - 1
    out.sort(key=lambda c: (c["r"], c["c"]))
    hdr = 0
    for r in range(R):
        row = [c for c in out if c["r"] == r and c["text"]]
        if row and sum(c["bold"] for c in row) / len(row) >= 0.7:
            hdr = r + 1
        else:
            break
    texts = [c for c in out if c["text"]]
    stats = {"cells": len(out), "empty_cells": len(out) - len(texts), "orphans": len(orphans),
             "glyphs_in_cells": sum(len(r["chars"]) for r in recs)}
    return {"rows": R, "cols": C, "header_rows": hdr, "bbox": [round(v, 1) for v in tb.bbox], "cells": out,
            "stats": stats}, consumed, orphans


def struct_to_md(st):
    R, C = st["rows"], st["cols"]
    if not R or not C:
        return ""
    m = [[""] * C for _ in range(R)]
    for c in st["cells"]:
        m[c["r"]][c["c"]] = c["text"]
    m = [r for r in m if any(r)] or m
    md = ["| " + " | ".join(m[0]) + " |", "|" + "---|" * C]
    md += ["| " + " | ".join(r) + " |" for r in m[1:]]
    return "\n".join(md)


def struct_to_html(st):
    import html as H
    out = ['<table dir="rtl">']
    for r in range(st["rows"]):
        row = [c for c in st["cells"] if c["r"] == r]
        if not row:
            continue
        out.append("<tr>")
        for c in sorted(row, key=lambda c: c["c"]):
            tag = "th" if r < st["header_rows"] else "td"
            sp = (f' rowspan="{c["rowspan"]}"' if c["rowspan"] > 1 else "") + (f' colspan="{c["colspan"]}"' if c["colspan"] > 1 else "")
            out.append(f"<{tag}{sp}>" + "<br>".join(H.escape(l) for l in c["lines"]) + f"</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "\n".join(out)


def table_to_md(page, tb, chars):            # kept for API compatibility
    r = build_table(page, tb, chars)
    return struct_to_md(r[0]) if r else ""


def dedupe(chars):
    """Drop faux-bold duplicates: same glyph drawn again within ~1.5pt."""
    out, grid = [], defaultdict(list)
    for c in chars:
        if c["text"] == "" or c["size"] <= 0:
            continue
        if c["text"].strip() and c["text"] not in ".-_·…":
            gx, gy = int(c["x0"] // 2), int(c["top"] // 2)
            nt = unicodedata.normalize("NFKC", c["text"])
            if any(unicodedata.normalize("NFKC", o["text"]) == nt and abs(o["x0"] - c["x0"]) < 1.5 and abs(o["top"] - c["top"]) < 1.5
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) for o in grid[(gx + dx, gy + dy)]):
                continue
            grid[(gx, gy)].append(c)
        out.append(c)
    return out


def drop_invisible(chars, pdfium_page, W, H, scale=2.5):
    """Some pages carry a hidden (clipped-out) duplicate of their text.  Extractors ignore
    clipping, so render the page and keep only glyphs that sit on visible ink."""
    img = pdfium_page.render(scale=scale, grayscale=True).to_numpy()
    if img.ndim == 3:
        img = img[..., 0]
    def ink(c):
        w, h = c["x1"] - c["x0"], c["bottom"] - c["top"]
        x0 = int((c["x0"] + 0.15 * w) * scale); x1 = max(int((c["x1"] - 0.15 * w) * scale), x0 + 1)
        y0 = int((c["top"] + 0.15 * h) * scale); y1 = max(int((c["bottom"] - 0.15 * h) * scale), y0 + 1)
        box = img[max(y0, 0):y1, max(x0, 0):x1]
        return bool(box.size and int(box.min()) < 140)

    groups = defaultdict(list)                  # hidden copy differs in text matrix from the visible one
    for c in chars:
        m = c.get("matrix") or (1, 0, 0, 1, 0, 0)
        groups[(round(m[3] / m[0], 1) if m[0] else 1, round(c["size"]), c.get("fontname", ""))].append(c)
    out = []
    for g in groups.values():
        for row in cluster_rows(g):
            vis = [c for c in row if c["text"].strip()]
            if not vis or sum(map(ink, vis)) / len(vis) >= 0.6:
                out.extend(row)
    return out



def ink_coverage(pdfium_page, chars, page, scale=2.0):
    """Self-audit. Renders the page and measures
      coverage = share of visible ink that lies under an extracted glyph (or a ruling line)
      ghost    = share of extracted glyphs that sit on blank paper
    Low coverage means content is NOT in the text layer (scan, vector text); high ghost means
    hidden text slipped through."""
    img = pdfium_page.render(scale=scale, grayscale=True).to_numpy()
    if img.ndim == 3:
        img = img[..., 0]
    hh, ww = img.shape
    ink = img < 150
    mask = np.zeros_like(ink)

    def mark(x0, t, x1, b, pad=1):
        a, c = max(int(x0 * scale) - pad, 0), max(int(t * scale) - pad, 0)
        mask[c:min(int(b * scale) + pad + 1, hh), a:min(int(x1 * scale) + pad + 1, ww)] = True

    glyphs = [c for c in chars if c["text"].strip()]
    for c in glyphs:
        mark(c["x0"], c["top"], c["x1"], c["bottom"])
    for ln in page.lines:
        mark(ln["x0"], ln["top"], ln["x1"], ln["bottom"], pad=2)
    for r in page.rects:                       # only the border of a rectangle, never its inside
        x0, t, x1, b = r["x0"], r["top"], r["x1"], r["bottom"]
        mark(x0, t, x1, t, 2); mark(x0, b, x1, b, 2); mark(x0, t, x0, b, 2); mark(x1, t, x1, b, 2)
    total = int(ink.sum())
    cov = float((ink & mask).sum()) / total if total else 1.0
    ghost = 0
    for c in glyphs:
        a, t = max(int(c["x0"] * scale), 0), max(int(c["top"] * scale), 0)
        box = ink[t:max(int(c["bottom"] * scale), t + 1), a:max(int(c["x1"] * scale), a + 1)]
        if not box.size or not box.any():
            ghost += 1
    return round(cov, 4), round(ghost / len(glyphs), 4) if glyphs else 0.0

def snap_marks(chars):
    """Combining marks (tanween, shadda ...) are drawn above/below the line, so row clustering used to put
    them in a row of their own and they were lost.  Give each mark the vertical extent of its nearest base letter."""
    import bisect
    mn = lambda c: bool(c["text"]) and all(unicodedata.category(ch) == "Mn" for ch in c["text"])
    bases = sorted((c for c in chars if c["text"].strip() and not mn(c) and c["text"] != ZW),
                   key=lambda c: (c["x0"] + c["x1"]) / 2)
    xs = [(c["x0"] + c["x1"]) / 2 for c in bases]
    for c in chars:
        if not mn(c):
            continue
        mc = (c["x0"] + c["x1"]) / 2
        lo, hi = bisect.bisect_left(xs, mc - 14), bisect.bisect_right(xs, mc + 14)
        best = None
        for b in bases[lo:hi]:                                   # every letter within 14 pt horizontally
            dy = abs(b["top"] - c["top"])
            dx = abs((b["x0"] + b["x1"]) / 2 - mc)
            if dy > 0.95 * max(c["size"], 6) or dx >= 14:      # a mark is within ~1 line of its own letter
                continue
            d = dx + 2.5 * dy                                    # nearest in 2-D: never a letter of the next line
            if best is None or d < best[0]:
                best = (d, b)
        if best:
            c["top"], c["bottom"] = best[1]["top"], best[1]["bottom"]
    return chars


def is_upright(c) -> bool:
    m = c.get("matrix")
    return not m or abs(m[1]) <= 0.3 * abs(m[0])


def rotated_info(page):
    """(degrees to rotate the page so sideways text becomes horizontal, number of sideways glyphs) or None."""
    cs = [c for c in page.chars if c["text"].strip() and c.get("matrix")]
    rot = [c for c in cs if abs(c["matrix"][1]) > 0.3 * abs(c["matrix"][0])]
    if len(rot) < 40 or len(rot) < 0.1 * len(cs):
        return None
    up = sum(1 for c in rot if c["matrix"][1] > 0)
    return (ROT_UP if up >= len(rot) / 2 else ROT_DOWN), len(rot)


ROT_UP, ROT_DOWN = 90, 270      # text running bottom->top needs /Rotate 90 to read upright


def extract_page(pk, pdf, pdm, pno: int) -> dict:
    """process_page, plus: sideways (rotated) text/tables are re-oriented on a one-page rotated copy and
    extracted there, then appended after the upright content of the page."""
    pg, pd = pdf.pages[pno - 1], (pdm[pno - 1] if pdm else None)
    info = rotated_info(pg)
    if not info:
        return process_page(pg, pno, pd)
    deg, nrot = info
    res = process_page(pg, pno, pd, only_upright=True, quiet=True)
    one = pikepdf.Pdf.new()
    one.pages.append(pk.pages[pno - 1])
    one.pages[0].Rotate = (int(one.pages[0].get("/Rotate", 0)) + deg) % 360
    b2 = io.BytesIO(); one.save(b2); b2.seek(0)
    with pdfplumber.open(b2) as pdf2:
        pd2 = pdfium.PdfDocument(b2.getvalue())[0] if (pdfium and np is not None) else None
        res2 = process_page(pdf2.pages[0], pno, pd2, only_upright=True, quiet=True)
    notes = [f"ROTATED CONTENT: {nrot} sideways glyphs re-oriented ({deg} deg) and appended after the upright text"]
    cov = ghost = None
    if pd is not None and np is not None:
        cov, ghost = ink_coverage(pd, [c for c in pg.chars if c["text"].strip()], pg)
        if cov < 0.90:
            notes.append(f"LOW COVERAGE ({cov:.0%} of visible ink is explained by extracted text): content may be missing")
    return {"page": pno, "layout": res2["layout"], "notes": notes, "coverage": cov, "ghost": ghost,
            "blocks": res["blocks"] + res2["blocks"]}


def drop_stacked_layers(rows):
    """Two copies of the same line drawn on top of each other (a visible line plus a hidden/outlined twin in
    another font and size).  They overlap on x by >=70%; keep the copy that spans more of the line."""
    out, dropped = [], 0
    for r in rows:
        vis = [c for c in r if c["text"].strip()]
        by = defaultdict(list)
        for c in vis:
            by[round(c["size"])].append(c)
        big = {k: v for k, v in by.items() if len(v) >= 8}
        if len(big) >= 2:
            keys = sorted(big, key=lambda k: -len(big[k]))[:2]
            a, b = big[keys[0]], big[keys[1]]
            sa = (min(c["x0"] for c in a), max(c["x1"] for c in a)); sb = (min(c["x0"] for c in b), max(c["x1"] for c in b))
            ov = min(sa[1], sb[1]) - max(sa[0], sb[0])
            def alnum(v):
                return "".join(c["text"] for c in sorted(v, key=lambda c: -c["x0"]) if c["text"].isalnum())
            ta, tb_ = alnum(a), alnum(b)
            same = False
            if len(tb_) >= 8 and len(ta) >= 8:
                import difflib
                sm = difflib.SequenceMatcher(None, ta, tb_, autojunk=False)
                same = sum(bl.size for bl in sm.get_matching_blocks()) >= 0.8 * len(tb_)
            if same and ov >= 0.7 * min(sa[1] - sa[0], sb[1] - sb[0]):
                kb = round(b[0]["size"])
                drop = {id(c) for c in r if round(c["size"]) == kb}
                r = [c for c in r if id(c) not in drop]
                dropped += 1
        out.append(r)
    return out, dropped


def process_page(page, pno: int, pdfium_page=None, only_upright=False, quiet=False) -> dict:
    W, H = float(page.width), float(page.height)
    chars = [c for c in dedupe(page.chars)                      # glyphs positioned off the page are never visible
             if -1 <= (c["x0"] + c["x1"]) / 2 <= W + 1 and -1 <= (c["top"] + c["bottom"]) / 2 <= H + 1]
    if only_upright:
        chars = [c for c in chars if is_upright(c)]
    squashed = sum(1 for c in chars if c.get("matrix") and abs(c["matrix"][0]) > 0.1 and abs(c["matrix"][3] / c["matrix"][0]) < 0.9)
    n_before = len(chars)
    if pdfium_page is not None and np is not None:
        chars = drop_invisible(chars, pdfium_page, W, H)
    hidden = n_before - len(chars)
    chars = snap_marks(chars)
    items: list[dict] = []
    # --- tables (ruled)
    used = []
    try:
        tables = [t for t in page.find_tables() if len(t.rows) >= 2 and max(len(r.cells) for r in t.rows) >= 2]
    except Exception:
        tables = []
    consumed_all, orphan_all = set(), []
    for tb in tables:
        x0, t, x1, b = tb.bbox
        try:
            res = build_table(page, tb, chars)
        except Exception:
            res = None
        if not res:
            continue
        st, consumed, orphans = res
        md = struct_to_md(st)
        if md and any(c["text"] for c in st["cells"]):
            items.append({"type": "table", "text": md, "x0": x0, "x1": x1, "top": t, "bottom": b, "size": 0, "bold": False,
                          "struct": st, "html": struct_to_html(st)})
            consumed_all |= consumed; orphan_all += orphans

    def in_table(c):
        return id(c) in consumed_all

    free = [c for c in chars if not in_table(c)]
    rows = cluster_rows(free)
    rows, n_stacked = drop_stacked_layers(rows)
    gut = find_gutter(rows, W)
    overlap_rows = 0                            # two long lines in different fonts stacked on the same spot
    for r in rows:
        by = defaultdict(list)
        for c in r:
            if c["text"].strip():
                by[c.get("fontname", "").split("+")[-1]].append(c)
        big = [v for v in by.values() if len(v) >= 30]
        if len(big) >= 2:
            sp = [(min(c["x0"] for c in v), max(c["x1"] for c in v)) for v in big[:2]]
            ov = min(sp[0][1], sp[1][1]) - max(sp[0][0], sp[1][0])
            if ov >= 0.7 * min(sp[0][1] - sp[0][0], sp[1][1] - sp[1][0]):
                overlap_rows += 1
    zones = column_zones(page, W)             # the printed vertical rule between the columns, and the page span it covers
    if zones:
        gut = (zones[0][0] - 1.5, zones[0][0] + 1.5)
    gc = (gut[0] + gut[1]) / 2 if gut else None
    for r in rows:
        zr = None
        if zones:
            ym = sum((c["top"] + c["bottom"]) / 2 for c in r) / len(r)
            zr = next((z for z in zones if z[1] - 4 <= ym <= z[2] + 4), None)
        if gut and (zr is not None or not zones) and not any(c["text"].strip() and c["x0"] < gut[1] - 1 and c["x1"] > gut[0] + 1 for c in r):
            parts = [("R", [c for c in r if (c["x0"] + c["x1"]) / 2 >= gc]),
                     ("L", [c for c in r if (c["x0"] + c["x1"]) / 2 < gc])]
            for col, ch in parts:
                if ch:
                    it = line_item(ch)
                    if it:
                        it["col"] = col; items.append(it)
                        if zr is not None:
                            it["zone"] = (zr[1], zr[2])
        else:
            it = line_item(r)
            if it:
                it["col"] = "F"; items.append(it)
    for it in items:
        if it["type"] == "table":
            wide = (it["x1"] - it["x0"]) > 0.55 * W or (gut and it["x0"] < gut[0] and it["x1"] > gut[1])
            it["col"] = "F" if (wide or not gut) else ("R" if (it["x0"] + it["x1"]) / 2 >= gc else "L")
    items.sort(key=lambda i: i["top"])
    ordered, buf = [], {"R": [], "L": []}

    def flush():
        for col in ("R", "L"):
            ordered.extend(sorted(buf[col], key=lambda i: i["top"]))
            buf[col] = []

    for it in items:
        if it["col"] == "F":
            flush(); ordered.append(it)
        else:
            buf[it["col"]].append(it)
    flush()
    blocks = paragraphs(ordered, W)
    notes = []
    if quiet:
        pass
    elif len(page.chars) < 60 and page.images:
        notes.append("RASTER PAGE: content is an image, there is no text layer to extract (needs OCR)")
    elif len(page.images) and sum(i["width"] * i["height"] for i in page.images) > 0.5 * W * H and len(page.chars) < 400:
        notes.append("MOSTLY RASTER: only a small part of this page has a text layer")
    if overlap_rows:
        notes.append(f"OVERLAPPING TEXT LINES in {overlap_rows} row(s): a hidden line sits under a visible one, those lines may be garbled, verify visually")
    if squashed > 50:
        notes.append("FORM WITH DUPLICATE HIDDEN TEXT LAYER: reading order of form fields may be mixed, verify visually")
    elif hidden > 0.15 * max(n_before, 1) and hidden > 40:
        notes.append(f"{hidden} hidden/off-screen glyphs were dropped (invisible text layer)")
    cov = ghost = None
    if pdfium_page is not None and np is not None and not quiet:
        cov, ghost = ink_coverage(pdfium_page, chars, page)
        if cov < 0.90 and not any("RASTER" in n for n in notes):
            notes.append(f"LOW COVERAGE ({cov:.0%} of visible ink is explained by extracted text): content may be missing")
    return {"page": pno, "layout": "two_columns" if gut else "single", "notes": notes,
            "coverage": cov, "ghost": ghost, "blocks": blocks}


def paragraphs(items, W):
    """Merge consecutive text lines of one column into paragraphs; keep headings/tables apart."""
    blocks, cur = [], None
    pitch = sorted(b["bottom"] - b["top"] for b in items if b["type"] == "line") or [10]
    pitch = pitch[len(pitch) // 2]
    colx = {}
    for it in items:
        if it["type"] == "line":
            c = colx.setdefault(it["col"], [it["x0"], it["x1"]])
            c[0] = min(c[0], it["x0"]); c[1] = max(c[1], it["x1"])

    def close():
        nonlocal cur
        if cur:
            blocks.append(cur); cur = None

    prev = None
    for it in items:
        if it["type"] == "table":
            close(); blocks.append({"type": "table", "text": it["text"], "html": it.get("html", ""), "table": it.get("struct")}); prev = None; continue
        txt = it["text"]
        heading = it["bold"] and len(txt) < 160
        new = (cur is None or prev is None or heading != (cur["type"] == "heading")
               or it["col"] != prev["col"] or it["top"] - prev["bottom"] > 0.55 * pitch
               or re.match(r"^(المادة|الفصل|الباب|القسم|الجزء)\s", txt) is not None
               or prev["x0"] - colx[prev["col"]][0] > 0.12 * (colx[prev["col"]][1] - colx[prev["col"]][0]))
        if new:
            close()
            cw = max(colx[it["col"]][1] - colx[it["col"]][0], 1)
            cur = {"type": "heading" if heading else "paragraph", "text": txt, "col": it["col"], "top": it["top"], "zone": it.get("zone"),
                   "indent": (colx[it["col"]][1] - it["x1"]) > 0.04 * cw}
        else:
            cur["text"] += " " + txt
        cw = max(colx[it["col"]][1] - colx[it["col"]][0], 1)
        cur["bottom"] = it["bottom"]
        cur["full_end"] = (it["x0"] - colx[it["col"]][0]) < 0.06 * cw       # last line runs to the left margin: text goes on
        prev = it
    close()
    return blocks


# ---------------------------------------------------------------------------
# 4. Output
# ---------------------------------------------------------------------------
def to_text(pages):
    out = []
    for p in pages:
        out.append(f"===== Page {p['page']} =====")
        for n in p.get("notes", []):
            out.append(f"[NOTE] {n}")
        for b in p["blocks"]:
            out.append(b["text"]); out.append("")
    return "\n".join(out)


def to_md(pages):
    out = []
    for p in pages:
        out.append(f"\n---\n<!-- page {p['page']} -->\n")
        for n in p.get("notes", []):
            out.append(f"> **NOTE:** {n}\n")
        for b in p["blocks"]:
            if b["type"] == "heading":
                out.append(f"\n## {b['text']}\n")
            else:
                out.append(b["text"] + "\n")
    return "\n".join(out)


def to_html(pages, title="BO extraction"):
    import html as H
    css = ("body{font-family:'Noto Naskh Arabic','DejaVu Sans',Arial,sans-serif;direction:rtl;margin:16px;line-height:1.6;font-size:15px}"
           "table{border-collapse:collapse;margin:10px 0;font-size:13px}td,th{border:1px solid #888;padding:3px 6px;vertical-align:top}"
           "th{background:#e8e8e8}h2{font-size:17px;margin:12px 0 4px}.pg{color:#888;border-top:2px solid #444;margin-top:18px}"
           ".note{color:#a40;font-size:12px}")
    out = [f"<!doctype html><meta charset='utf-8'><title>{H.escape(title)}</title><style>{css}</style>"]
    for p in pages:
        out.append(f"<div class='pg'>page {p['page']}</div>")
        for n in p.get("notes", []):
            out.append(f"<div class='note'>{H.escape(n)}</div>")
        for b in p["blocks"]:
            if b["type"] == "table":
                out.append(b.get("html") or "<pre>" + H.escape(b["text"]) + "</pre>")
            elif b["type"] == "heading":
                out.append(f"<h2>{H.escape(b['text'])}</h2>")
            else:
                out.append(f"<p>{H.escape(b['text'])}</p>")
    return "\n".join(out)


def parse_pages(spec, n):
    if not spec:
        return list(range(1, n + 1))
    s = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1); s.update(range(int(a), int(b) + 1))
        else:
            s.add(int(part))
    return sorted(p for p in s if 1 <= p <= n)


TERMINAL = tuple(".:؛;؟?!…")
HEAD_RE = re.compile(r"^(المادة|الفصل|الباب|القسم|الجزء|الفرع|قرار|مرسوم|ظهير|مقرر|قانون|بلاغ|رأي|وعلى|وبعد|بناء|\d+\s*[-–.)]|[-–•*]\s)")
HDR_RE = re.compile(r"(عدد\s*\d{3,}|الجريدة الرسمية)")


def join_split_paragraphs(pages):
    """A sentence cut by a column or page break comes out as two blocks.  Re-join them: a paragraph that does not
    end with sentence punctuation, followed (next column / next page, after the running header) by a block that
    does not start like a new paragraph (no first-line indent, no heading keyword / bullet), is one paragraph.
    The continuation block is removed from its page and its text appended to the earlier block, which records
    "joined_pages"."""
    prev, n = None, 0
    for pg in pages:
        body = [b for b in pg["blocks"] if b.get("top") is not None and b["type"] in ("paragraph", "heading")
                and not (len(b["text"]) < 170 and HDR_RE.search(b["text"]) and re.search(r"\d{3,}", b["text"]))]
        pg["_btop"] = min((b["top"] for b in body), default=0); pg["_bbot"] = max((b["bottom"] for b in body), default=0)
        pg["_prev_bbot"] = None
    for pg in pages:
        keep, first = [], True
        for b in pg["blocks"]:
            if first and b["type"] in ("paragraph", "heading") and len(b["text"]) < 170 and HDR_RE.search(b["text"]) and re.search(r"\d{3,}", b["text"]):
                keep.append(b); first = False; continue            # running header: transparent
            first = False
            ok = (prev is not None and b["type"] == "paragraph" and prev["type"] == "paragraph"
                  and not b.get("indent") and not HEAD_RE.match(b["text"])
                  and not prev["text"].rstrip().endswith(TERMINAL) and prev.get("full_end")
                  and not re.search(r"…\s*\d*\s*$", prev["text"]) and re.search(r"\w", b["text"])
                  and len(re.sub(r"[\s*.…]", "", b["text"])) > 3
                  and (prev.get("col") != b.get("col") or prev["_page"] != pg["page"])
                  and b.get("top") is not None and b["top"] <= (b["zone"][0] if b.get("zone") else pg["_btop"]) + 45   # starts at the top of its column/page
                  and prev["bottom"] >= (prev["zone"][1] if prev.get("zone") else prev["_bbot"]) - 45)               # previous one ended at the bottom
            if ok:
                prev["text"] = prev["text"].rstrip() + " " + b["text"]
                prev.setdefault("joined_pages", [prev["_page"]])
                if pg["page"] not in prev["joined_pages"]:
                    prev["joined_pages"].append(pg["page"])
                n += 1
                continue
            b["_page"] = pg["page"]; b["_bbot"] = pg["_bbot"]
            keep.append(b)
            prev = b if b["type"] in ("paragraph", "heading") else None
        pg["blocks"] = keep
        # a trailing footer-like page number must not block joining: nothing to do, kept as is
    for pg in pages:
        for k in ("_btop", "_bbot", "_prev_bbot"):
            pg.pop(k, None)
        for b in pg["blocks"]:
            for k in ("_page", "_bbot", "top", "bottom", "full_end", "zone"):
                b.pop(k, None)
    return n


def link_continued_tables(pages):
    """A table whose last row is cut by the page break continues on the next page: when page N ends with a
    table and page N+1 opens (after the running header line) with a table of the same width, mark the second one
    "continues_previous" so a consumer can stitch them (header rows are repeated or not, we do not guess)."""
    for a, b in zip(pages, pages[1:]):
        if b["page"] != a["page"] + 1:
            continue
        ta = next((x for x in reversed(a["blocks"]) if x["type"] == "table" and x.get("table")), None)
        if ta is None or a["blocks"][-1] is not ta:
            continue
        tb = next((x for x in b["blocks"][:3] if x["type"] == "table" and x.get("table")), None)
        if tb is not None and tb["table"]["cols"] == ta["table"]["cols"]:
            tb["continues_previous"] = True
            tb["table"]["continues_previous"] = True


def run_one(a, pdf_path, prefix):

    pk = pikepdf.open(pdf_path)
    st = repair(pk)
    st["blanked"] = strip_clipped_text(pk)
    buf = io.BytesIO(); pk.save(buf)
    if a.save_fixed:
        Path(a.save_fixed).write_bytes(buf.getvalue())
    buf.seek(0)
    print(f"font repair: {st['fonts_fixed']} Sakkal fonts, {st['codes_changed']} glyph mappings corrected; "
          f"{st['blanked']} clipped (invisible) text strings removed", file=sys.stderr)
    if st.get("fffd_fixed") or st.get("fffd_left"):
        print(f"  unreadable letters (U+FFFD in the font's own map): {st['fffd_fixed']} repaired from glyph_fixes.json, "
              f"{st['fffd_left']} left as U+FFFD", file=sys.stderr)
        if st["fffd_left"]:
            print("  -> letters of a font that is not in glyph_fixes.json yet: see README 'Unreadable letters' (learn_glyphs.py)", file=sys.stderr)
    if st["unverified"]:                       # one short line (full lists with --report)
        tot = sum(len(g) for g in st["unverified"].values())
        print(f"  note: {tot} unverified glyph ids in {len(st['unverified'])} font(s) (rarely used symbols; --report lists them)", file=sys.stderr)
        if a.report:
            for base, gids in st["unverified"].items():
                print(f"    {base}: {sorted(f'{g:04X}' for g in gids)}", file=sys.stderr)

    pages = []
    pdm = pdfium.PdfDocument(buf.getvalue()) if pdfium else None
    with pdfplumber.open(buf) as pdf:
        for pno in parse_pages(a.pages, len(pdf.pages)):
            pages.append(extract_page(pk, pdf, pdm, pno))
            if a.report:
                for n in pages[-1]["notes"]:
                    print(f"  page {pno}: {n}", file=sys.stderr)
            if a.report:
                print(f"page {pno:3}: {pages[-1]['layout']:12} blocks={len(pages[-1]['blocks'])}", file=sys.stderr)
    link_continued_tables(pages)
    joined = 0 if a.no_join else join_split_paragraphs(pages)
    if joined:
        print(f"joined {joined} paragraph(s) split by a column/page break", file=sys.stderr)
    flagged = [p for p in pages if p["notes"]]
    covs = [p["coverage"] for p in pages if p.get("coverage") is not None]
    clean = [p for p in pages if not p["notes"] and (p.get("coverage") or 0) >= 0.97 and (p.get("ghost") or 0) <= 0.02]
    ink_ok = sum(1 for c in covs if c >= 0.97)
    print(f"AUDIT: {len(pages)} pages | fully trusted (no flags, ink coverage >= 97%, ghost <= 2%): {len(clean)} "
          f"({100 * len(clean) / max(len(pages), 1):.1f}%) | flagged: {len(flagged)} | "
          f"mean ink coverage {100 * sum(covs) / max(len(covs), 1):.1f}%", file=sys.stderr)
    if a.audit and not a.no_audit:
      Path(f"{prefix}.audit.json").write_text(json.dumps([{"page": p["page"], "coverage": p.get("coverage"), "ghost": p.get("ghost"),
                                       "notes": p["notes"]} for p in pages], ensure_ascii=False, indent=1), encoding="utf-8")
    if a.format in ("txt", "all"):
        Path(f"{prefix}.txt").write_text(repair_text(to_text(pages)), encoding="utf-8")
    if a.format in ("md", "all"):
        Path(f"{prefix}.md").write_text(repair_text(to_md(pages)), encoding="utf-8")
    if a.format in ("html", "all"):
        Path(f"{prefix}.html").write_text(repair_text(to_html(pages, Path(pdf_path).name)), encoding="utf-8")
    if a.format in ("json", "all"):
        Path(f"{prefix}.json").write_text(repair_text(json.dumps(pages, ensure_ascii=False, indent=1)), encoding="utf-8")
    ras = [p["page"] for p in pages if any(n.startswith("MOSTLY RASTER") for n in p["notes"])]
    low = [p["page"] for p in pages if any(n.startswith("LOW COVERAGE") for n in p["notes"])]
    if ras:
        print(f"  !! scanned/image-only pages (no text layer, text NOT in the .md): {ras}", file=sys.stderr)
    if low:
        print(f"  !! low ink coverage (some content missing): {low}", file=sys.stderr)
    print(f"done -> {prefix}.{'md' if a.format == 'md' else '[' + a.format + ']'}", file=sys.stderr)
    return {"raster": ras, "low": low, "pages": len(pages)}


def _work(a, pdf):
    """one PDF in a worker process: returns (log text, result, error)"""
    import contextlib, os
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            r = run_one(a, pdf, Path(pdf).with_suffix(""))
        return buf.getvalue(), r, None
    except Exception as e:                       # one bad PDF must not stop the batch
        return buf.getvalue(), None, repr(e)


def main():
    ap = argparse.ArgumentParser(description="Accurate Arabic BO PDF extractor (no OCR)")
    ap.add_argument("pdf", nargs="?", help="a PDF file, or a folder (all sub-folders are searched, one .md is written next to each PDF)")
    ap.add_argument("--build-labels", nargs="+", metavar="PDF", help="(re)build sakkal_labels.json from PDFs that have a ToUnicode")
    ap.add_argument("-o", "--out")
    ap.add_argument("-p", "--pages")
    ap.add_argument("--no-join", action="store_true", help="keep paragraphs split by column/page breaks as separate blocks")
    ap.add_argument("-f", "--format", choices=["txt", "md", "json", "html", "all"], default="md", help="default: md only")
    ap.add_argument("--overwrite", action="store_true", help="folder mode: re-extract PDFs that already have a .md")
    ap.add_argument("--jobs", "-j", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                    help="folder mode: PDFs extracted in parallel (default: CPU cores - 1; use 1 for no parallelism)")
    ap.add_argument("--audit", action="store_true", help="also write <name>.audit.json (per-page coverage)")
    ap.add_argument("--no-audit", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--report", action="store_true", help="print font-repair report")
    ap.add_argument("--save-fixed", help="also write the repaired PDF here")
    a = ap.parse_args()
    if a.build_labels:
        build_labels(a.build_labels); return
    if not a.pdf:
        ap.error("pdf (file or folder) required")
    src = Path(a.pdf)
    if src.is_dir():
        # whole folder (all sub-folders): one .md next to every PDF, nothing else is written
        a.format, a.no_audit = "md", True
        pdfs = sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
        print(f"{len(pdfs)} PDF(s) under {src}", file=sys.stderr)
        done = skipped = 0; failed = []; gaps = []
        todo = []
        for k, p in enumerate(pdfs, 1):
            out = Path(f"{p.with_suffix('')}.md")
            if out.exists() and not a.overwrite:
                skipped += 1; print(f"[{k}/{len(pdfs)}] skip (exists): {out}", file=sys.stderr); continue
            todo.append((k, p))
        jobs = max(1, min(a.jobs, len(todo))) if todo else 1
        print(f"{len(todo)} to extract, {skipped} already done, {jobs} parallel worker(s)", file=sys.stderr)

        def finish(k, p, log, r, err):
            nonlocal done
            print(f"[{k}/{len(pdfs)}] {p}\n{log}", end="", file=sys.stderr)
            if err:
                failed.append((str(p), err)); print(f"  FAILED: {err}", file=sys.stderr)
            else:
                done += 1
                if r and (r["raster"] or r["low"]):
                    gaps.append((str(p), r))

        if jobs == 1:
            for k, p in todo:
                finish(k, p, *_work(a, str(p)))
        else:
            from concurrent.futures import ProcessPoolExecutor, as_completed
            with ProcessPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(_work, a, str(p)): (k, p) for k, p in todo}
                for fu in as_completed(futs):
                    k, p = futs[fu]
                    try:
                        finish(k, p, *fu.result())
                    except Exception as e:             # worker crashed (e.g. out of memory)
                        finish(k, p, "", None, repr(e))
        print(f"FOLDER DONE: {done} extracted, {skipped} skipped, {len(failed)} failed", file=sys.stderr)
        for f, e in failed:
            print(f"  failed: {f}: {e}", file=sys.stderr)
        if gaps:
            print(f"{len(gaps)} PDF(s) have image-only / low-coverage pages (content missing from the .md):", file=sys.stderr)
            for f, r in gaps:
                print(f"  {f}: {len(r['raster'])} image-only, {len(r['low'])} low-coverage of {r['pages']} pages", file=sys.stderr)
        return
    run_one(a, str(src), Path(a.out) if a.out else src.with_suffix(""))


if __name__ == "__main__":
    main()
