"""Automatic clean-up of a newly extracted Bulletin Officiel issue, before it is split into articles.

Wrong letters caused by the PDF's fonts are already repaired by the extractor (extract_bo_pdf.py, with fonttools). This step joins
Arabic words the PDF text layer split with a stray space («عل يها» -> «عليها», «ا لسادس» -> «السادس»). A pair is joined only when
the joined word is common in the installed law pack and the pieces are not words of their own, so two real words side by side are
never joined. The text as extracted is kept in <md_dir>/raw/ and every change is listed in <md_dir>/raw/<issue>.changes.txt.

The letter-swap repair of tools/repair_arabic_text.py is NOT run here: on clean text it also "corrects" good words that are
missing from the dictionary (names, new terms), so it stays a manual tool whose report is read by a person."""
from __future__ import annotations

import collections
import shutil
import sqlite3
from pathlib import Path

from ..text.repair import fixer, spacing_vocab


def pack_vocabulary(pack_path: Path) -> collections.Counter:
    """Arabic word counts of the installed law pack (read-only)."""
    con = sqlite3.connect(f"file:{pack_path}?mode=ro", uri=True)
    try:
        return spacing_vocab(t for (t,) in con.execute("SELECT text FROM provision_text WHERE lang='ar'"))
    finally:
        con.close()


def clean_issue(md: Path, vocab: collections.Counter) -> list[str]:
    """Repairs one extracted issue in place; returns the changes made ("A B -> AB")."""
    text = md.read_text(encoding="utf-8")
    new, done = fixer(vocab)(text)
    if done:
        raw = md.parent / "raw"
        raw.mkdir(exist_ok=True)
        shutil.copy2(md, raw / md.name)
        counts = collections.Counter(done)
        (raw / f"{md.stem}.changes.txt").write_text("\n".join(f"{c}  x{n}" for c, n in counts.most_common()), encoding="utf-8")
        md.write_text(new, encoding="utf-8")
    return done
