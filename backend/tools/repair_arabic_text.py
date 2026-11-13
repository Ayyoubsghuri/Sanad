#!/usr/bin/env python3
"""Repair an Arabic PDF whose text layer swaps neighbouring letters («املادة» for «المادة», «الرشيف» for «الشريف», «رمق» for «رقم»).

The swaps are local, so a corrupted word has the same letters as the right word: it is looked up, by its letters, in a dictionary built from clean
texts of the same domain (your other law files).  Detached final letters («القاض ي») are joined.  Only words not known as they stand are touched, and
a change is made only when exactly one best candidate exists; everything else is listed in the report so it can be checked by eye."""
from __future__ import annotations

import argparse
import collections
import glob
import re
import sys
import unicodedata
from pathlib import Path

AR = "ء-ي"
_WORD = re.compile(rf"[{AR}]+")
_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه"})


def clean(t: str) -> str:
    t = re.sub("[‪-‮‎‏⁦-⁩؜]", "", t)
    t = unicodedata.normalize("NFKC", t)
    return re.sub("[ً-ٰٟـ]", "", t)


def key(w: str) -> str:
    return "".join(sorted(w.translate(_FOLD)))


def dl(a: str, b: str) -> int:
    """Damerau-Levenshtein (adjacent transposition counts 1)."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


PHRASES = [("أن واحد", "آن واحد"), ("المادة الولي", "المادة الأولى"), ("ربيع لأول", "ربيع الأول"), ("ربيع لآخر", "ربيع الآخر"), ("الجريدة الرسمية عدد", "الجريدة الرسمية عدد")]


class Repairer:
    def __init__(self, vocab: collections.Counter, min_known: int = 2, bigrams: collections.Counter | None = None):
        self.vocab = vocab
        self.big = bigrams or collections.Counter()
        self.min_known = min_known
        self.index: dict[str, list[str]] = collections.defaultdict(list)
        for w, n in vocab.items():
            if n >= 1 and len(w) >= 2:  # candidates may be rare words; "known as it stands" needs min_known
                self.index[key(w)].append(w)
        self.changed: collections.Counter = collections.Counter()
        self.ambiguous: collections.Counter = collections.Counter()
        self.unresolved: collections.Counter = collections.Counter()

    def known(self, w: str) -> bool:
        return self.vocab.get(w, 0) >= self.min_known

    @staticmethod
    def derive(w: str) -> list[str]:
        """The two corruptions this PDF makes, undone: (1) a lam-alef ligature stored backwards («الكالم» for «الكلام», «األمر» for «الأمر», «إال» for «إلا»);
        (2) the article's lam pushed behind the next letter («املحضر» for «المحضر», «اذلكر» for «الذكر», «ابملادة» for «بالمادة»).  Every combination is tried."""
        outs: set[str] = set()
        # (1) positions where an alef-type letter is followed by lam: swap them
        pos = [i for i in range(len(w) - 1) if w[i] in "اأإآ" and w[i + 1] == "ل"]
        for mask in range(1, 1 << min(len(pos), 6)):
            t = list(w)
            for k, i in enumerate(pos[:6]):
                if mask >> k & 1:
                    t[i], t[i + 1] = t[i + 1], t[i]
            outs.add("".join(t))
        # (2) word start (after one optional prefix letter): ا X ل -> ا ل X, also after (1)
        for base in list(outs) + [w]:
            m = re.match(rf"^([وفبكل]?)ا([{AR}])ل(?=[{AR}])", base)
            if m and m.group(2) != "ل":
                outs.add(base[: len(m.group(1))] + "ال" + m.group(2) + base[len(m.group(0)):])
                if m.group(1) in ("ب", "ك", "ل"):  # «ابملادة» = ب + ال + مادة
                    pass
            m = re.match(rf"^ا([بكل])([{AR}])ل(?=[{AR}])", base)  # «ابملادة» -> «بالمادة»
            if m:
                outs.add(m.group(1) + "ال" + m.group(2) + base[len(m.group(0)):])
        outs.discard(w)
        return list(outs)

    @staticmethod
    def alef_twins(w: str) -> list[str]:
        """The same word with another form of its first alef: أن / آن / إن / ان (the ligature lost the mark)."""
        if w and w[0] in "اأإآ":
            return [c + w[1:] for c in "اأإآ" if c != w[0]]
        return []

    def fix_word(self, w: str, prev: str = "", nxt: str = "") -> str:
        if len(w) <= 3 and len(w) >= 2:  # «يف» for «في», «مت» for «تم»: a short word whose swap is overwhelmingly more common
            near = [c for c in self.index.get(key(w), []) if c != w and dl(w, c) == 1]
            if near:
                b = max(near, key=lambda c: self.vocab[c])
                if self.vocab[b] >= 100 * max(1, self.vocab.get(w, 0)):
                    self.changed[(w, b)] += 1
                    return b
        if self.known(w) and len(w) >= 2:  # «ثالث» / «ثلاث», «أن» / «آن»: both are words; the neighbours decide
            twins = [c for c in self.derive(w) + self.alef_twins(w) if self.vocab.get(c, 0) >= 3]
            if twins:
                here = self.big.get((prev, w), 0) + self.big.get((w, nxt), 0)
                best = max(twins, key=lambda c: self.big.get((prev, c), 0) + self.big.get((c, nxt), 0))
                there = self.big.get((prev, best), 0) + self.big.get((best, nxt), 0)
                if there >= 2 and there >= 3 * max(1, here):
                    self.changed[(w, best)] += 1
                    return best
        if self.known(w) or len(w) < 2:
            return w
        # a dropped hamza: «النسان» -> «الإنسان», «لدارة» -> «لإدارة», «الرهاب» -> «الإرهاب»
        ins = {w[:i] + h + w[i:] for i in range(1, min(len(w), 4)) for h in "إأآ"}
        ins = [c for c in ins if self.vocab.get(c, 0) >= 2]
        if ins and not self.known(w):
            best = max(ins, key=lambda c: (self.big.get((prev, c), 0) + self.big.get((c, nxt), 0), self.vocab[c]))
            self.changed[(w, best)] += 1
            return best
        # first: the known corruption rules; the candidate with the most corpus support wins
        rc = [c for c in self.derive(w) if self.vocab.get(c, 0) >= 1]
        if rc:
            best = max(rc, key=lambda c: (self.big.get((prev, c), 0) + self.big.get((c, nxt), 0), self.vocab[c]))
            self.changed[(w, best)] += 1
            return best
        cands = [c for c in self.index.get(key(w), []) if c != w and dl(w, c) <= 2]
        if cands:
            def score(c: str) -> tuple:
                ctx = self.big.get((prev, c), 0) + self.big.get((c, nxt), 0)
                return (-ctx, dl(w, c), -self.vocab[c])
            scored = sorted(cands, key=score)
            best = scored[0]
            if len(scored) == 1 or score(best)[:2] != score(scored[1])[:2] or self.vocab[best] >= 3 * self.vocab[scored[1]]:
                self.changed[(w, best)] += 1
                return best
            self.ambiguous[(w, best, scored[1])] += 1
            self.changed[(w, best)] += 1
            return best
        sp = self.split_merged(w)
        if sp != w:
            return sp
        self.unresolved[w] += 1
        return w

    def fix_line(self, line: str) -> str:
        # detached final letter: «القاض ي» -> «القاضي»
        def join(m):
            w = m.group(1)
            a, b = self.vocab.get(w + "ى", 0), self.vocab.get(w + "ي", 0)
            if max(a, b) >= self.min_known:
                return w + ("ى" if a > b else "ي")
            return m.group(0) if self.known(w) else w + ("ى" if m.group(2) == "ى" else "ي")

        line = re.sub(rf"([{AR}]{{2,}}) ([يى])(?![{AR}])", join, line)
        ws = list(_WORD.finditer(line))
        out, last = [], 0
        fixed: list[str] = []
        for k, m in enumerate(ws):
            prev = fixed[-1] if fixed else ""
            nxt = ws[k + 1].group(0) if k + 1 < len(ws) else ""
            f = self.fix_word(m.group(0), prev, nxt)
            fixed.append(f)
            out.append(line[last:m.start()])
            out.append(f)
            last = m.end()
        out.append(line[last:])
        line = "".join(out)
        line = re.sub(rf"(?<![{AR}])(و|ف)?ال(?![{AR}])", lambda m: (m.group(1) or "") + "لا", line)  # a lone «ال» is «لا»
        for bad, good in PHRASES:
            line = line.replace(bad, good)
        return self.join_fragments(line)

    def join_fragments(self, line: str) -> str:
        """«اس تثنائية» -> «استثنائية», «ش يء» -> «شيء»: a word broken in two where the pieces are not words of their own and the whole is one."""
        ws = list(_WORD.finditer(line))
        if len(ws) < 2:
            return line
        out, last, k = [], 0, 0
        while k < len(ws):
            m = ws[k]
            if k + 1 < len(ws) and line[m.end():ws[k + 1].start()] == " ":
                a, b = m.group(0), ws[k + 1].group(0)
                ab = a + b
                solid = max(self.vocab.get(ab, 0), self.vocab.get(ab.replace("ى", "ي"), 0))
                weak_piece = self.vocab.get(a, 0) < 20 or self.vocab.get(b, 0) < 20 or len(a) <= 2 or len(b) <= 2
                if solid >= 2 and weak_piece and not (self.vocab.get(a, 0) >= 20 and self.vocab.get(b, 0) >= 20):
                    out.append(line[last:m.start()])
                    out.append(ab)
                    last = ws[k + 1].end()
                    self.changed[(a + " " + b, ab)] += 1
                    k += 2
                    continue
            k += 1
        out.append(line[last:])
        return "".join(out)

    def split_merged(self, w: str) -> str:
        """«األمربجريمة» -> two words, when the whole is unknown and exactly one split gives two well-known words."""
        if self.known(w) or len(w) < 8:
            return w
        opts = [(w[:i], w[i:]) for i in range(3, len(w) - 2) if self.vocab.get(w[:i], 0) >= 8 and self.vocab.get(w[i:], 0) >= 8]
        if len(opts) == 1:
            self.changed[(w, " ".join(opts[0]))] += 1
            return " ".join(opts[0])
        return w


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
