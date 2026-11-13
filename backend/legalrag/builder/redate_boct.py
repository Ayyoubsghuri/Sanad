"""Correct the issue dates of BOCT issues already in the pack, without re-embedding.

    py -m legalrag.builder.redate_boct data/boct            (report: stored date -> date read from the file)
    py -m legalrag.builder.redate_boct data/boct --apply

The date is read from the issue's cover / running header (see from_boct.issue_info); data/boct/dates.json ({"30": "2012-05-09"}) overrides it.
Only the date columns change (instrument + version validity); the passages and their vectors are untouched."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from .from_boct import to_sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    from ..config import Settings
    from ..state import build_context, install_pack
    from ..store.localkey import local_private_key
    from ..store.signing import sign_pack

    s = Settings()
    ctx = build_context(s)
    if not ctx.pack_usable():
        print("no usable law pack:", ctx.pack_error)
        return 2
    dest = s.resolved_lawpack_path()
    db = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    stored = dict(db.execute("SELECT instrument_id, bo_date FROM instrument WHERE instrument_id LIKE 'MA_BOCT_%'").fetchall())
    db.close()
    changes: dict[str, str] = {}
    for f in sorted(Path(a.folder).rglob("*.md")):
        if f.name.upper().startswith("BO_"):
            continue
        src, rep = to_sources(f)
        if src is None or rep.get("date_guessed"):
            continue
        iid = src["instruments"][0]["instrument_id"]
        if iid in stored and stored[iid] != rep["date"]:
            changes[iid] = rep["date"]
            print(f"  {iid:14} {stored[iid]} -> {rep['date']}")
    print(f"{len(changes)} issue(s) to correct, {len(stored) - len(changes)} already right")
    if not a.apply or not changes:
        if changes:
            print("run again with --apply to write them")
        return 0
    work = dest.with_name("update-work.db")
    shutil.copy2(dest, work)
    work.with_suffix(".db.sig").unlink(missing_ok=True)
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-redate"
    con = sqlite3.connect(work)
    for iid, d in changes.items():
        con.execute("UPDATE instrument SET bo_date=?, promulgation_date=?, effective_date=?, status_note=REPLACE(status_note, '; ISSUE DATE NOT FOUND, 2000-01-01 is a placeholder: set the real date', '') WHERE instrument_id=?", (d, d, d, iid))
        con.execute("UPDATE provision_version SET valid_from=? WHERE provision_id IN (SELECT provision_id FROM provision WHERE instrument_id=?)", (d, iid))
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
    print("done: dates corrected, pack re-signed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
