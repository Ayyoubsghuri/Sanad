#!/usr/bin/env python3
"""learn_glyphs.py - teach the extractor the letters a font's own map can't read (U+FFFD).

The extractor repairs them automatically once glyph_fixes.json knows the font.  A font it has never seen stays U+FFFD
(it says so at the end of the run).  Teaching it takes four steps:

  1. collect   py learn_glyphs.py collect  NEW.pdf [MORE.pdf ...]
       finds every unreadable glyph, gives each a private placeholder letter, writes them into glyph_fixes.json
       (nothing visible changes yet), and writes glyph_sheet_<pdf>.png: the shape of every new glyph with its tag.
  2. extract in learning mode (placeholders stay in the text):
       set BO_FFFD_PUA=glyph_fixes.json   (Windows:  set BO_FFFD_PUA=glyph_fixes.json)
       py extract_bo_pdf.py NEW.pdf -o NEW_learn.md
  3. list the groups still without text and their contexts, write what each one spells into labels.json:
       py learn_glyphs.py inv  NEW_learn.md [--top 40] [--skip N]
       py learn_glyphs.py ctx  NEW_learn.md "6954:6293|6954:6338"
       labels.json:  {"6954:6293|6954:6338": "ير", "6954:5677": "ي", ...}      ("" = a stray dot, drop it)
  4. py learn_glyphs.py merge labels.json      (adds them to glyph_fixes.json)
     then extract normally (unset BO_FFFD_PUA) and every bulletin with that font is repaired.

  py learn_glyphs.py status NEW_learn.md       how much of the damage is labelled
"""
import collections
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXES = Path(os.environ.get("BO_GLYPH_FIXES") or HERE / "glyph_fixes.json")
POOL = [chr(c) for c in list(range(0x750, 0x780)) + list(range(0x8A0, 0x8C8)) + list(range(0x870, 0x89F)) + list(range(0x7C0, 0x7EB))]


def load():
    d = json.loads(FIXES.read_text(encoding="utf-8")) if FIXES.exists() else {}
    for k in ("hash", "groups", "clusters", "words", "subs"):
        d.setdefault(k, {})
    return d


def save(d):
    FIXES.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")


def tagmap(d):
    return {v: k for k, v in d["groups"].items()}          # placeholder -> "glyph count:gid"


def collect(pdfs):
    sys.path.insert(0, str(HERE))
    import extract_bo_pdf as E
    import pikepdf
    d = load()
    used = set(d["groups"].values())
    pool = [c for c in POOL if c not in used]
    new = {}
    for p in pdfs:
        pdf = pikepdf.open(p)
        for f in E.all_fonts(pdf).values():
            if str(f.get("/Subtype")) != "/Type0" or "/ToUnicode" not in f:
                continue
            bad = [g for g, v in E.parse_tounicode(f).items() if "�" in v]
            t = E.type0_ttf(f) if bad else None
            if t is None:
                continue
            order = t.getGlyphOrder(); n = len(order)
            for g in bad:
                h = E.glyph_hash(t, g, order) if 0 < g < n else None
                if not h or h in d["hash"]:
                    continue
                k = f"{n}:{g}"
                if k not in d["groups"]:
                    d["groups"][k] = pool.pop(0)
                d["hash"][h] = d["groups"][k]
                new[h] = (E.font_family(f), n, g, t, order)
        if new:
            sheet(new, d, Path(p).stem)
    save(d)
    print(f"{len(new)} new unreadable glyph(s); glyph_fixes.json updated ({len(d['hash'])} known in total)")


def sheet(new, d, stem):
    try:
        from PIL import Image, ImageDraw
        from fontTools.pens.freetypePen import FreeTypePen
    except Exception:
        print("  (Pillow/freetype not available: no glyph sheet)"); return
    cell, cols = 110, 10
    items = list(new.items())
    im = Image.new("L", (cols * cell, ((len(items) + cols - 1) // cols) * cell), 255)
    dr = ImageDraw.Draw(im)
    for i, (h, (fam, n, g, t, order)) in enumerate(items):
        x, y = (i % cols) * cell, (i // cols) * cell
        try:
            pen = FreeTypePen(t.getGlyphSet())
            t.getGlyphSet()[order[g]].draw(pen)
            gi = pen.image(width=cell - 10, height=cell - 30, contain=True)
            im.paste(255 - gi.getchannel("A") if gi.mode == "RGBA" else gi, (x + 5, y + 2))
        except Exception:
            pass
        dr.text((x + 3, y + cell - 24), f"{n}:{g}", fill=0)
    out = f"glyph_sheet_{stem}.png"
    im.save(out); print("  glyph shapes:", out)


def runs(text, d):
    rev = tagmap(d)
    rx = re.compile("[" + "".join(sorted(rev)) + "]+")
    return rev, rx


def inv(md, top, skip):
    d = load(); rev, rx = runs("", d)
    t = Path(md).read_text(encoding="utf-8")
    cl = d["clusters"]
    tag = lambda s: "|".join(rev[c] for c in s)
    cnt = collections.Counter(m.group(0) for m in rx.finditer(t))
    word = re.compile("[ء-ي" + "".join(sorted(rev)) + "]+")
    ex = collections.defaultdict(collections.Counter)
    for w in word.findall(t):
        for m in rx.finditer(w):
            ex[m.group(0)][w] += 1
    todo = [(k, n) for k, n in cnt.most_common() if k not in cl]
    tot = sum(cnt.values()); lab = sum(n for k, n in cnt.items() if k in cl)
    print(f"runs {len(cnt)}, occurrences {tot}, labelled {100 * lab / max(tot, 1):.1f}%, to do {len(todo)}")
    show = lambda w: "".join(f"<{rev[c]}>" if c in rev else c for c in w)
    for k, n in todo[skip:skip + top]:
        print(f"{tag(k):<28} x{n:<6}", "  ".join(f"{show(w)}({c})" for w, c in ex[k].most_common(5)))


def ctx(md, want, n=6):
    d = load(); rev, rx = runs("", d)
    k = 0; seen = set()
    for line in Path(md).read_text(encoding="utf-8").splitlines():
        for m in rx.finditer(line):
            if "|".join(rev[c] for c in m.group(0)) == want:
                a = "".join(f"<{rev[c]}>" if c in rev else c for c in line[max(0, m.start() - 28):m.end() + 28])
                if a not in seen:
                    seen.add(a); print(a); k += 1
                break
        if k >= n:
            break


def merge(labels_path):
    d = load()
    inv_groups = {k: v for k, v in d["groups"].items()}
    lab = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    for k, v in lab.items():
        if k == "_words":
            d["words"].update(v); continue
        if k == "_subs":
            continue
        run = "".join(inv_groups.get(t, t) for t in k.split("|"))     # a token that is not a glyph tag is literal (a stray dot letter, "*")
        d["clusters"][run] = v
    for k, v in lab.get("_subs", {}).items():
        d["subs"][k] = v
    save(d); print(f"{len(d['clusters'])} labelled runs in glyph_fixes.json")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("collect", "inv", "ctx", "merge", "status"):
        print(__doc__); sys.exit(1)
    if a[0] == "collect":
        collect(a[1:])
    elif a[0] in ("inv", "status"):
        top = int(a[a.index("--top") + 1]) if "--top" in a else (0 if a[0] == "status" else 40)
        skip = int(a[a.index("--skip") + 1]) if "--skip" in a else 0
        inv(a[1], top, skip)
    elif a[0] == "ctx":
        ctx(a[1], a[2])
    elif a[0] == "merge":
        merge(a[1])
