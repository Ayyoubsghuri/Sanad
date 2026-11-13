"""Join Arabic words that a PDF text layer split with a stray space («يتف ق» -> «يتفق», «عل يها» -> «عليها», «ي حدد» -> «يحدد»).

    py tools\\fix_spacing.py                  report: how many joins, per law, with examples (nothing is changed)
    py tools\\fix_spacing.py --apply          repair the installed pack (stop the backend first), re-sign it

A pair "A B" is joined only when the joined word AB is a common word in YOUR pack, and A or B is not a word on its own (a single letter, or a
piece that almost never occurs alone).  Two real words side by side («في هذا», «من القانون») are never joined.  The article texts and the search
index are updated; the vectors are kept (a joined word changes them very little).  Quotes the checker compares are taken from the same
updated text, so answers stay verifiable."""
from __future__ import annotations

import argparse
import collections
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORD = re.compile(r"[ء-ي]+")
STOP = {"و", "في", "من", "أو", "او", "لا", "ما", "أن", "ان", "إن", "عن", "على", "علي", "ثم", "قد", "لم", "لن", "هو", "هي", "أي", "اي", "إلى", "الى",
        "مع", "كل", "بين", "حتى", "إذا", "اذا", "التي", "الذي", "هذا", "هذه", "ذلك", "تلك", "غير", "بعد", "قبل", "عند", "أما", "كما", "بل"}


def build_vocab(rows) -> collections.Counter:
    v: collections.Counter = collections.Counter()
    for (t,) in rows:
        v.update(WORD.findall(t or ""))
    return v


def fixer(vocab: collections.Counter):
    tok = re.compile(r"[\u0621-\u064A]+|[^\u0621-\u064A]+")

    def ok(a: str, b: str) -> bool:
        ab = a + b
        if a in STOP or b in STOP or len(ab) < 3 or (len(a) == 1 and len(b) == 1) or len(a) > 6 or len(b) > 12:
            return False
        pieces = max((vocab[x] for x in (a, b) if len(x) >= 2), default=0)
        # the joined word must be common, and clearly more common than any piece of two letters or more: then the space is a PDF error
        return vocab[ab] >= 8 and vocab[ab] >= 3 * pieces

    def fix(text: str) -> tuple[str, list[str]]:
        done: list[str] = []
        parts = tok.findall(text or "")
        out: list[str] = []
        i = 0
        while i < len(parts):
            p = parts[i]
            # word, one plain space, word: every neighbouring pair is looked at (a join can be followed by another: «ا لفا تورة»)
            if out and p == " " and i + 1 < len(parts) and WORD.fullmatch(out[-1]) and WORD.fullmatch(parts[i + 1]) and ok(out[-1], parts[i + 1]):
                done.append(f"{out[-1]} {parts[i + 1]} -> {out[-1] + parts[i + 1]}")
                out[-1] = out[-1] + parts[i + 1]
                i += 2
                continue
            out.append(p)
            i += 1
        return "".join(out), done

    return fix


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", help="only the instruments whose id starts with this (e.g. LAW_15.95_2026)")
    a = ap.parse_args(argv)
    from legalrag.config import Settings
    from legalrag.state import build_context, install_pack
    from legalrag.store.localkey import local_private_key
    from legalrag.store.signing import sign_pack
    from legalrag.text.arabic import keyword_text

    s = Settings()
    ctx = build_context(s)
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    dest = s.resolved_lawpack_path()
    db = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    print("reading the vocabulary of your pack ...")
    vocab = build_vocab(db.execute("SELECT text FROM provision_text WHERE lang='ar'"))
    fix = fixer(vocab)
    where = "AND p.instrument_id LIKE ?" if a.only else ""
    args = (a.only + "%",) if a.only else ()
    rows = db.execute("SELECT pt.pv_id, pt.text, p.instrument_id FROM provision_text pt JOIN provision_version pv ON pv.pv_id=pt.pv_id "
                      f"JOIN provision p ON p.provision_id=pv.provision_id WHERE pt.lang='ar' {where}", args).fetchall()
    changes: dict[int, str] = {}
    per: collections.Counter = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for pv_id, text, iid in rows:
        new, done = fix(text or "")
        if done:
            changes[pv_id] = new
            per[iid] += len(done)
            if len(examples[iid]) < 4:
                examples[iid] += done[: 4 - len(examples[iid])]
    print(f"{sum(per.values())} joins in {len(changes)} article(s) of {len(per)} text(s)")
    for iid, n in per.most_common(25):
        print(f"  {iid:28} {n:5}   e.g. " + " | ".join(examples[iid]))
    if not a.apply or not changes:
        if changes:
            print("check the examples above, then run again with --apply (backend stopped)")
        return 0
    chunks = db.execute(f"SELECT chunk_id, pv_id, body, text FROM chunk WHERE lang='ar' AND pv_id IN ({','.join('?' * len(changes))})", list(changes)).fetchall()
    db.close()
    work = dest.with_name("update-work.db")
    shutil.copy2(dest, work)
    work.with_suffix(".db.sig").unlink(missing_ok=True)
    con = sqlite3.connect(work)
    for pv_id, new in changes.items():
        con.execute("UPDATE provision_text SET text=? WHERE pv_id=? AND lang='ar'", (new, pv_id))
    for cid, _pv, body, etext in chunks:
        b2, t2 = fix(body or "")[0], fix(etext or "")[0]
        if b2 != body or t2 != etext:
            con.execute("UPDATE chunk SET body=?, text=?, keyword_text=? WHERE chunk_id=?", (b2, t2, keyword_text(t2), cid))
    print("rebuilding the search index ...")
    con.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-spacing"
    con.execute("INSERT INTO pack_meta(key,value) VALUES('pack_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (version,))
    con.commit()
    con.close()
    key = local_private_key(s) if (ctx.pack_trust and ctx.pack_trust.state == "signed_valid") else None
    if key:
        sign_pack(work, key, datetime.now(timezone.utc).isoformat(timespec="seconds"), version)
    try:
        install_pack(ctx, work, work.with_suffix(".db.sig") if work.with_suffix(".db.sig").exists() else None)
    finally:
        work.unlink(missing_ok=True)
        work.with_suffix(".db.sig").unlink(missing_ok=True)
    print("done: words joined, search index rebuilt, pack re-signed (restart the backend)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
