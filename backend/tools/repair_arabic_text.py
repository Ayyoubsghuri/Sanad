#!/usr/bin/env python3
"""Repair an Arabic PDF whose text layer swaps neighbouring letters («املادة» for «المادة», «الرشيف» for «الشريف», «رمق» for «رقم»).

The swaps are local, so a corrupted word has the same letters as the right word: it is looked up, by its letters, in a dictionary built from clean
texts of the same domain (your other law files).  Detached final letters («القاض ي») are joined.  Only words not known as they stand are touched, and
a change is made only when exactly one best candidate exists; everything else is listed in the report so it can be checked by eye."""
from __future__ import annotations

import argparse
import collections
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from legalrag.text.repair import _WORD, Repairer, clean  # noqa: E402


def build_vocab(patterns: list[str]) -> tuple[collections.Counter, collections.Counter]:
    v: collections.Counter = collections.Counter()
    b: collections.Counter = collections.Counter()
    for pat in patterns:
        for f in glob.glob(pat, recursive=True):
            for line in clean(Path(f).read_text("utf-8")).split("\n"):
                ws = _WORD.findall(line)
                for i, w in enumerate(ws):
                    v[w] += 1
                    if i:
                        b[(ws[i - 1], w)] += 1
    return v, b


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("raw", help="text file with <!-- page N --> markers, or plain text")
    ap.add_argument("--vocab", nargs="+", required=True, help="clean .md/.txt files or globs")
    ap.add_argument("--out", required=True)
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    vocab, big = build_vocab(a.vocab)
    text = clean(Path(a.raw).read_text("utf-8"))
    rp = Repairer(vocab, bigrams=big)
    out = "\n".join(rp.fix_line(l) for l in text.split("\n"))
    # second pass: what the document itself says often (after the first repair) is added to the dictionary
    own = collections.Counter(_WORD.findall(out))
    vocab2 = collections.Counter(vocab)
    for w, n in own.items():
        if n >= 3 and len(w) >= 3:
            vocab2[w] += n
    rp = Repairer(vocab2, bigrams=big)
    out = "\n".join(rp.fix_line(l) for l in text.split("\n"))
    Path(a.out).write_text(out, encoding="utf-8")
    toks = _WORD.findall(out)
    known = sum(1 for t in toks if rp.known(t))
    print(f"words {len(toks)}  known after repair {100 * known / max(1, len(toks)):.1f}%  corrected {sum(rp.changed.values())}  unresolved distinct {len(rp.unresolved)}")
    if a.report:
        lines = ["CHANGED (word -> word, times):"] + [f"  {w} -> {c}  x{n}" for (w, c), n in rp.changed.most_common(300)]
        lines += ["", "AMBIGUOUS (kept the first):"] + [f"  {w} -> {c} | {d}  x{n}" for (w, c, d), n in rp.ambiguous.most_common(200)]
        lines += ["", "UNRESOLVED (most frequent):"] + [f"  {w}  x{n}" for w, n in rp.unresolved.most_common(400)]
        Path(a.report).write_text("\n".join(lines), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
