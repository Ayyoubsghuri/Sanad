"""Move the start date of a text in the pack (it was installed with its publication date, but applies later), without re-embedding.

    py -m legalrag.builder.redate LAW_58.25 --from 2026-08-24              (report: what would change)
    py -m legalrag.builder.redate LAW_58.25 --from 2026-08-24 --apply

Every article version of that instrument that is still open and starts BEFORE the new date gets valid_from = the new date, and the
instrument's effective date is set to it.  Versions that start later are left alone.  Nothing is deleted; the pack is re-signed."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import date, datetime, timezone


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("instrument_id", nargs="+")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM-DD: the day the text starts to apply")
    ap.add_argument("--note", default="")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    date.fromisoformat(a.start)
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
    todo: list[str] = []
    for iid in a.instrument_id:
        row = db.execute("SELECT title_ar, title_fr, kind, number, effective_date FROM instrument WHERE instrument_id=?", (iid,)).fetchone()
        if not row:
            print(f"  {iid}: not in the pack")
            continue
        n, total, first = db.execute(
            "SELECT SUM(pv.valid_from < ? AND (pv.valid_to IS NULL OR pv.valid_to > ?)), COUNT(*), MIN(pv.valid_from) FROM provision_version pv "
            "JOIN provision p ON p.provision_id=pv.provision_id WHERE p.instrument_id=?", (a.start, a.start, iid)).fetchone()
        print(f"  {iid}: {row[0] or row[1]}  ({row[2]} {row[3]})  effective {row[4]}, first version {first}  -> "
              f"{n or 0} of {total} article version(s) start on {a.start}")
        if n:
            todo.append(iid)
    db.close()
    if not a.apply or not todo:
        if todo:
            print("check the title above, then run again with --apply")
        return 0
    work = dest.with_name("update-work.db")
    shutil.copy2(dest, work)
    work.with_suffix(".db.sig").unlink(missing_ok=True)
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-redate"
    con = sqlite3.connect(work)
    for iid in todo:
        con.execute("UPDATE provision_version SET valid_from=? WHERE valid_from < ? AND (valid_to IS NULL OR valid_to > ?) AND provision_id IN "
                    "(SELECT provision_id FROM provision WHERE instrument_id=?)", (a.start, a.start, a.start, iid))
        note = f"applies from {a.start}" + (f": {a.note}" if a.note else "")
        con.execute("UPDATE instrument SET effective_date=?, status_note=TRIM(COALESCE(status_note,'') || '; ' || ?, '; ') WHERE instrument_id=?",
                    (a.start, note, iid))
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
    print("done: start date moved, pack re-signed (restart the backend)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
