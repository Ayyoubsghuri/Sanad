"""End an old text in the pack when a newer edition of the same law was installed next to it, without re-embedding.

    py -m legalrag.builder.retire ORDER_1309.77 --until 2024-01-01            (report: what would change)
    py -m legalrag.builder.retire ORDER_1309.77 --until 2024-01-01 --apply

Every article version of that instrument that is still in force gets valid_to = the date (exclusive), so a question about today uses
the new edition only, and a question dated before still finds the old one.  Nothing is deleted; the pack is re-signed."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import date, datetime, timezone


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("instrument_id", nargs="+")
    ap.add_argument("--until", help="YYYY-MM-DD: the old text stops applying on this day")
    ap.add_argument("--all-dates", action="store_true", help="hide the old text for every date (a better copy of the SAME edition was installed)")
    ap.add_argument("--note", default="", help="e.g. 'replaced by the 2024 edition'")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if not a.all_dates:
        if not a.until:
            ap.error("give --until YYYY-MM-DD or --all-dates")
        date.fromisoformat(a.until)
    else:
        a.until = "9999-12-31"
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
        row = db.execute("SELECT title_ar, title_fr, kind, number FROM instrument WHERE instrument_id=?", (iid,)).fetchone()
        if not row:
            print(f"  {iid}: not in the pack")
            continue
        n_open, n_all = db.execute(
            "SELECT SUM(pv.valid_to IS NULL AND pv.valid_from < ?), COUNT(*) FROM provision_version pv JOIN provision p ON p.provision_id=pv.provision_id "
            "WHERE p.instrument_id=?", (a.until, iid)).fetchone()
        when = "hidden for every date" if a.all_dates else f"end on {a.until}"
        print(f"  {iid}: {row[0] or row[1]}  ({row[2]} {row[3]})  -> {n_open or 0} of {n_all} article version(s) {when}")
        if n_open:
            todo.append(iid)
    db.close()
    if not a.apply or not todo:
        if todo:
            print("check the title above, then run again with --apply")
        return 0
    work = dest.with_name("update-work.db")
    shutil.copy2(dest, work)
    work.with_suffix(".db.sig").unlink(missing_ok=True)
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-retire"
    con = sqlite3.connect(work)
    for iid in todo:
        if a.all_dates:
            con.execute("UPDATE provision_version SET valid_to=valid_from WHERE valid_to IS NULL AND provision_id IN "
                        "(SELECT provision_id FROM provision WHERE instrument_id=?)", (iid,))
            note = "replaced by a better copy" + (f": {a.note}" if a.note else "")
        else:
            con.execute("UPDATE provision_version SET valid_to=? WHERE valid_to IS NULL AND valid_from < ? AND provision_id IN "
                        "(SELECT provision_id FROM provision WHERE instrument_id=?)", (a.until, a.until, iid))
            note = f"no longer applied from {a.until}" + (f": {a.note}" if a.note else "")
        con.execute("UPDATE instrument SET status_note=TRIM(COALESCE(status_note,'') || '; ' || ?, '; ') WHERE instrument_id=?", (note, iid))
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
    print("done: old text ended, pack re-signed (restart the backend)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
