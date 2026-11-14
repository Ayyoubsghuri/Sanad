"""Automatic repair of new Arabic legal text before it goes into the pack (used by the Bulletin Officiel update).

PDF text layers damage Arabic in a few repeatable ways.  This module repairs only the cases it can decide safely, using the vocabulary of the
texts already in the pack (millions of words of clean legislation):

1. a word split by a stray space («يتف ق» -> «يتفق», «ا لمادة» -> «المادة»), joined only when the whole is a common word and a piece is not;
2. a final letter left on its own («القاض ي» -> «القاضي»);
3. the lam of the article pushed behind the next letter or a lam-alef stored backwards («املادة» -> «المادة», «األمر» -> «الأمر»), only for a
   word that is NOT known as it stands and when exactly one repair is a common word.

A word that is already a known word is never changed, numbers and punctuation are never touched, and every change is listed so it can be
checked.  Anything less certain is left as it is (tools/repair_arabic_text.py does the deeper, reviewed repair)."""
from __future__ import annotations

import collections
import re
import sqlite3
from pathlib import Path

AR = "ء-ي"
WORD = re.compile(rf"[{AR}]+")
TOK = re.compile(rf"[{AR}]+|[^{AR}]+")
STOP = {"و", "في", "من", "أو", "او", "لا", "ما", "أن", "ان", "إن", "عن", "على", "علي", "ثم", "قد", "لم", "لن", "هو", "هي", "أي", "اي", "إلى", "الى",
        "مع", "كل", "بين", "حتى", "إذا", "اذا", "التي", "الذي", "هذا", "هذه", "ذلك", "تلك", "غير", "بعد", "قبل", "عند", "أما", "كما", "بل"}


class Cleaner:
    def __init__(self, vocab: collections.Counter, min_join: int = 8, min_known: int = 3):
        self.v = vocab
        self.min_join = min_join
        self.min_known = min_known

    # ------------------------------------------------------------------ building
    @classmethod
    def from_pack(cls, db_path: Path) -> "Cleaner":
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            v: collections.Counter = collections.Counter()
            for (t,) in con.execute("SELECT text FROM provision_text WHERE lang='ar'"):
                v.update(WORD.findall(t or ""))
        finally:
            con.close()
        return cls(v)

    def usable(self) -> bool:
        return sum(self.v.values()) >= 50_000  # too small a vocabulary decides nothing safely

    # ------------------------------------------------------------------ rules
    def _join_ok(self, a: str, b: str) -> bool:
        ab = a + b
        if a in STOP or b in STOP or len(ab) < 3 or (len(a) == 1 and len(b) == 1) or len(a) > 6 or len(b) > 12:
            return False
        pieces = max((self.v[x] for x in (a, b) if len(x) >= 2), default=0)
        return self.v[ab] >= self.min_join and self.v[ab] >= 3 * pieces

    @staticmethod
    def _variants(w: str) -> set[str]:
        out: set[str] = set()
        pos = [i for i in range(len(w) - 1) if w[i] in "اأإآ" and w[i + 1] == "ل"]  # lam-alef stored backwards
        for mask in range(1, 1 << min(len(pos), 4)):
            t = list(w)
            for k, i in enumerate(pos[:4]):
                if mask >> k & 1:
                    t[i], t[i + 1] = t[i + 1], t[i]
            out.add("".join(t))
        for base in list(out) + [w]:  # «املادة» -> «المادة», «واملحكمة» -> «والمحكمة», «ابملادة» -> «بالمادة»
            m = re.match(rf"^([وفبكل]?)ا([{AR}])ل(?=[{AR}])", base)
            if m and m.group(2) != "ل":
                out.add(base[: len(m.group(1))] + "ال" + m.group(2) + base[len(m.group(0)):])
            m = re.match(rf"^ا([بكل])([{AR}])ل(?=[{AR}])", base)
            if m:
                out.add(m.group(1) + "ال" + m.group(2) + base[len(m.group(0)):])
        m = re.match(rf"^([وفبكل]?ال)([{AR}]{{3,}})$", w)  # the alef of a lam-alef ligature lost: «الستغلال» -> «الاستغلال»
        if m and m.group(2)[0] != "ا":
            out.add(m.group(1) + "ا" + m.group(2))
        out.discard(w)
        return out

    def _fix_word(self, w: str) -> str:
        if self.v.get(w, 0) >= 2 or len(w) < 5:  # short unknown words are mostly names («بالل»): left alone
            return w
        good = sorted((c for c in self._variants(w) if self.v.get(c, 0) >= self.min_join), key=lambda c: -self.v[c])
        if not good:
            return w
        if len(good) == 1 or self.v[good[0]] >= 3 * self.v[good[1]]:
            return good[0]
        return w

    # ------------------------------------------------------------------ text
    def clean(self, text: str) -> tuple[str, list[str]]:
        """Returns the repaired text and the list of changes ("old -> new")."""
        changes: list[str] = []
        out_lines = []
        for line in (text or "").split("\n"):
            if line.lstrip().startswith(("<!--", "```")):
                out_lines.append(line)
                continue

            def tail(m: re.Match) -> str:  # «القاض ي» -> «القاضي»
                w, ch = m.group(1), m.group(2)
                for c in (w + ch, w + ("ي" if ch == "ى" else "ى")):
                    if self.v.get(c, 0) >= self.min_known and self.v.get(w, 0) < self.min_known:
                        changes.append(f"{w} {ch} -> {c}")
                        return c
                return m.group(0)

            line = re.sub(rf"([{AR}]{{2,}}) ([يى])(?![{AR}])", tail, line)
            parts = TOK.findall(line)
            out: list[str] = []
            i = 0
            while i < len(parts):
                p = parts[i]
                if out and p == " " and i + 1 < len(parts) and WORD.fullmatch(out[-1]) and WORD.fullmatch(parts[i + 1]) and self._join_ok(out[-1], parts[i + 1]):
                    changes.append(f"{out[-1]} {parts[i + 1]} -> {out[-1] + parts[i + 1]}")
                    out[-1] = out[-1] + parts[i + 1]
                    i += 2
                    continue
                out.append(p)
                i += 1
            for k, p in enumerate(out):
                if WORD.fullmatch(p):
                    f = self._fix_word(p)
                    if f != p:
                        changes.append(f"{p} -> {f}")
                        out[k] = f
            out_lines.append("".join(out))
        return "\n".join(out_lines), changes

    def clean_file(self, path: Path, raw_dir: Path | None = None) -> list[str]:
        """Repairs a text file in place; the original is first copied into raw_dir (a separate folder, so it is never read as a new file)."""
        text = path.read_text(encoding="utf-8")
        new, changes = self.clean(text)
        if changes:
            if raw_dir is not None:
                raw_dir.mkdir(parents=True, exist_ok=True)
                (raw_dir / path.name).write_text(text, encoding="utf-8")
            path.write_text(new, encoding="utf-8")
        return changes
