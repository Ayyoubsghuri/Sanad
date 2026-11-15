r"""Make the phone version of the law pack (for the Sanad Android app).

    py tools\make_mobile_pack.py                      # reads your installed pack, writes mobile_out\
    py tools\make_mobile_pack.py --db C:\path\current.db --out mobile_out

It keeps what the phone needs to search the law, with every dated version of each article (valid_from / valid_to), so the
phone answers with the law in force on the date the user picks (the app's "as of" date; today by default):
  sanad_mobile.db    the passages (quotable text + law, article, Bulletin Officiel) and a keyword index (SQLite FTS4, which every Android has)
  sanad_mobile.vec   the bge-m3 vectors, 1 byte per number instead of 4 (int8 + one scale per passage), read from disk by the phone
  manifest.json      sizes and SHA-256 of both files (the app checks them after downloading)

Upload the three files to your Hugging Face dataset in a folder "mobile" (scripts\PUBLISH_MOBILE_PACK_HF.bat does it).
The keyword index stores the same words as your PC pack (keyword_text), so the phone's search finds what the PC finds."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAGIC = b"SNDVEC1\0"
TRUSTED = ("verified", "single_source", "derived")  # same as the PC app (draft and disputed texts are not used)
AUTHORITY = {"constitution": 0, "organic_law": 1, "treaty": 2, "law": 2, "dahir_law": 2, "code": 2, "decree": 3, "order": 4, "circular": 5,
             "administrative_guidance": 6, "court_decision": 7}
CF_MODEL = "@cf/baai/bge-m3"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def pick_embedder(con: sqlite3.Connection, wanted: str | None) -> tuple[str, str, int]:
    rows = con.execute("SELECT e.embedder_id, e.model, e.dim, COUNT(ce.chunk_id) FROM embedder e LEFT JOIN chunk_embedding ce ON ce.embedder_id=e.embedder_id "
                       "GROUP BY e.embedder_id ORDER BY 4 DESC").fetchall()
    if not rows:
        raise SystemExit("the pack has no vectors")
    for eid, model, dim, _n in rows:
        if wanted is None or eid == wanted:
            return eid, model, int(dim)
    raise SystemExit(f"no embedder {wanted!r} in the pack; it has {[r[0] for r in rows]}")


def build(db: Path, out: Path, as_of: str | None = None, embedder: str | None = None, langs: tuple[str, ...] = ("ar", "fr")) -> dict:
    """as_of=None keeps every version (the default: the phone filters by date); a date keeps only the versions in force then."""
    out.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    eid, model, dim = pick_embedder(src, embedder)
    pack_version = (src.execute("SELECT value FROM pack_meta WHERE key='pack_version'").fetchone() or [None])[0]
    lang_sql = ",".join("?" for _ in langs)
    rows = src.execute(
        f"""SELECT c.chunk_id, c.lang, c.body, c.keyword_text, p.instrument_id, p.number AS art, p.suffix, i.kind, i.number AS inum, i.title_ar, i.title_fr,
                   i.bo_number, i.bo_date, i.domain, pv.valid_from, pv.valid_to, ce.vector
            FROM chunk c JOIN provision_version pv ON pv.pv_id=c.pv_id JOIN provision p ON p.provision_id=pv.provision_id
            JOIN instrument i ON i.instrument_id=p.instrument_id
            LEFT JOIN chunk_embedding ce ON ce.chunk_id=c.chunk_id AND ce.embedder_id=?
            WHERE c.edition='official' AND c.lang IN ({lang_sql})
              {"AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?)" if as_of else ""}
              AND pv.verification_status IN ('verified','single_source','derived')
            ORDER BY i.instrument_id, p.number_int, p.suffix, pv.valid_from, c.chunk_id""",
        (eid, *langs, *((as_of, as_of) if as_of else ())))

    dbp, vecp = out / "sanad_mobile.db", out / "sanad_mobile.vec"
    for p in (dbp, vecp, out / "sanad_mobile.vec.part"):
        p.unlink(missing_ok=True)
    dst = sqlite3.connect(dbp)
    dst.executescript("""
        PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA page_size=4096;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE passage (id INTEGER PRIMARY KEY, chunk_id INTEGER NOT NULL, lang TEXT NOT NULL, instrument_id TEXT NOT NULL, kind TEXT NOT NULL,
                              authority INTEGER NOT NULL, law_number TEXT, law_title TEXT, article TEXT, bo TEXT, domain TEXT, valid_from TEXT, body TEXT NOT NULL,
                              has_vector INTEGER NOT NULL, valid_to TEXT);
        CREATE INDEX passage_dates ON passage(valid_from, valid_to);
        CREATE VIRTUAL TABLE passage_fts USING fts4(content="", kw);
        CREATE TABLE stopword (w TEXT PRIMARY KEY) WITHOUT ROWID;
    """)
    from legalrag.text import stopwords
    dst.executemany("INSERT OR IGNORE INTO stopword VALUES (?)", [(w,) for w in sorted(stopwords.ALL) if w])

    tmp = out / "sanad_mobile.vec.part"
    scales: list[float] = []
    n = with_vec = 0
    zero = np.zeros(dim, dtype=np.int8)
    with open(tmp, "wb") as vf:
        batch_p, batch_f = [], []
        for r in rows:
            n += 1
            v = np.frombuffer(r["vector"], dtype=np.float32) if r["vector"] is not None else None
            if v is not None and v.shape[0] == dim and np.isfinite(v).all() and np.linalg.norm(v) > 0:
                v = v / np.linalg.norm(v)
                s = float(np.abs(v).max() / 127.0) or 1.0
                vf.write(np.round(v / s).astype(np.int8).tobytes())
                scales.append(s)
                with_vec += 1
            else:
                vf.write(zero.tobytes())
                scales.append(0.0)  # no vector: the phone skips this row in the meaning search
            art = (r["art"] or "") + (f" {r['suffix']}" if r["suffix"] else "")
            title = r["title_ar"] if r["lang"] == "ar" else (r["title_fr"] or r["title_ar"])
            bo = " ".join(x for x in (f"BO {r['bo_number']}" if r["bo_number"] else "", r["bo_date"] or "") if x)
            batch_p.append((n, r["chunk_id"], r["lang"], r["instrument_id"], r["kind"], AUTHORITY.get(r["kind"], 9), r["inum"], title, art, bo, r["domain"],
                            r["valid_from"], r["body"], 1 if scales[-1] else 0, r["valid_to"]))
            batch_f.append((n, r["keyword_text"] or ""))
            if len(batch_p) >= 5000:
                dst.executemany("INSERT INTO passage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch_p)
                dst.executemany("INSERT INTO passage_fts(docid, kw) VALUES (?,?)", batch_f)
                batch_p, batch_f = [], []
                print(f"\r  {n:,} passages", end="", flush=True)
        if batch_p:
            dst.executemany("INSERT INTO passage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch_p)
            dst.executemany("INSERT INTO passage_fts(docid, kw) VALUES (?,?)", batch_f)
    print(f"\r  {n:,} passages, {with_vec:,} with a vector")
    if not n:
        raise SystemExit("no passage" + (f" in force on {as_of}" if as_of else ""))
    src.close()

    # vector file = header + scales + int8 rows (row i belongs to passage id i+1)
    with open(vecp, "wb") as out_f, open(tmp, "rb") as body:
        out_f.write(MAGIC + struct.pack("<ii", n, dim))
        out_f.write(np.asarray(scales, dtype="<f4").tobytes())
        while b := body.read(1 << 22):
            out_f.write(b)
    tmp.unlink()

    built = datetime.now(timezone.utc).isoformat(timespec="seconds")
    version = f"{datetime.now(timezone.utc):%Y.%m.%d.%H%M}-mobile"
    meta = {"version": version, "built_at": built, "as_of": as_of or "all versions", "dated": "1", "source_pack_version": pack_version or "", "embedder_id": eid, "model": model,
            "cloudflare_model": CF_MODEL, "dim": str(dim), "passages": str(n), "with_vector": str(with_vec)}
    dst.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    dst.commit()
    dst.execute("INSERT INTO passage_fts(passage_fts) VALUES('optimize')")
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    manifest = {**meta, "dim": dim, "passages": n, "with_vector": with_vec,
                "files": {"db": {"name": dbp.name, "size": dbp.stat().st_size, "sha256": sha256(dbp)},
                          "vec": {"name": vecp.name, "size": vecp.stat().st_size, "sha256": sha256(vecp)}}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="the full pack (default: the installed one)")
    ap.add_argument("--out", default="mobile_out")
    ap.add_argument("--date", help="keep only the law in force on this date (default: every version, so the phone can answer for any date)")
    ap.add_argument("--embedder", help="embedder id (default: the one with the most vectors)")
    a = ap.parse_args()
    if a.db:
        db = Path(a.db)
    else:
        from legalrag.config import Settings
        db = Settings().resolved_lawpack_path()
    if not db.exists():
        print(f"no pack at {db}")
        return 1
    print(f"reading {db} ...")
    m = build(db, Path(a.out), a.date, a.embedder)
    mb = lambda k: m["files"][k]["size"] / 1e6  # noqa: E731
    print(f"\nmobile pack {m['version']}: {m['passages']:,} passages ({m['with_vector']:,} with vectors), embedder {m['embedder_id']} ({m['model']}, {m['dim']} dims)")
    print(f"  sanad_mobile.db   {mb('db'):,.0f} MB\n  sanad_mobile.vec  {mb('vec'):,.0f} MB\n  manifest.json\nin {Path(a.out).resolve()}")
    if "m3" not in (m["model"] or "").lower():
        print(f"\nWARNING: the vectors come from {m['model']}, not bge-m3: Cloudflare's bge-m3 will not match them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
