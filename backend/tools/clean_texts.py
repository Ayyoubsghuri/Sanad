r"""Repair damaged Arabic words in text files BEFORE you import them by hand (the BO update in the app does this by itself).

    py tools\clean_texts.py data\boct\*.md                 report only: what would change, nothing is written
    py tools\clean_texts.py data\boct\*.md --apply         repair the files (the originals are copied into a folder "raw" next to them)

What it repairs (only when certain, using the vocabulary of your installed pack): a word split by a stray space («يتف ق» -> «يتفق»), a final
letter on its own («القاض ي» -> «القاضي»), a backwards lam-alef or a misplaced lam («املادة» -> «المادة», «األمر» -> «الأمر»).
Known words are never changed.  For the pack already installed, use tools\fix_spacing.py; for heavily damaged PDFs, tools\repair_arabic_text.py."""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legalrag.config import Settings  # noqa: E402
from legalrag.text.cleanup import Cleaner  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="files or patterns (*.md, *.txt)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--db", help="pack to take the vocabulary from (default: the installed one)")
    a = ap.parse_args(argv)
    files = [Path(f) for p in a.files for f in (glob.glob(p) or [p]) if Path(f).is_file()]
    if not files:
        print("no file found")
        return 1
    db = Path(a.db) if a.db else Settings().resolved_lawpack_path()
    if not db.exists():
        print(f"no pack at {db}: the vocabulary comes from it")
        return 1
    print("reading the vocabulary of your pack ...")
    c = Cleaner.from_pack(db)
    if not c.usable():
        print("the pack is too small to decide repairs safely")
        return 1
    total = 0
    for f in files:
        if a.apply:
            ch = c.clean_file(f, raw_dir=f.parent / "raw")
        else:
            ch = c.clean(f.read_text(encoding="utf-8"))[1]
        total += len(ch)
        if ch:
            print(f"{f}: {len(ch)} change(s)   e.g. " + " | ".join(ch[:4]))
    print(f"\n{total} change(s) in {len(files)} file(s)" + ("" if a.apply else "   (report only: run again with --apply to write them)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
