import json
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def test_mobile_pack_has_passages_index_and_vectors(tmp_path, pack_path):
    import make_mobile_pack as mm
    m = mm.build(Path(pack_path), tmp_path, "2026-10-27")
    assert m["passages"] > 0 and m["files"]["db"]["sha256"] and json.loads((tmp_path / "manifest.json").read_text())["passages"] == m["passages"]
    con = sqlite3.connect(tmp_path / "sanad_mobile.db")
    n = con.execute("SELECT COUNT(*) FROM passage").fetchone()[0]
    assert n == m["passages"]
    # the keyword index finds passage 1 by a word of its keyword text, and gives the counts the phone ranks with (BM25 from matchinfo)
    cid1 = con.execute("SELECT chunk_id FROM passage WHERE id=1").fetchone()[0]
    kwt = sqlite3.connect(pack_path).execute("SELECT keyword_text FROM chunk WHERE chunk_id=?", (cid1,)).fetchone()[0]
    word = max(kwt.split(), key=len)
    rows = con.execute("SELECT docid, matchinfo(passage_fts,'pcnalx') FROM passage_fts WHERE passage_fts MATCH ?", ('"' + word + '"',)).fetchall()
    assert 1 in [r[0] for r in rows] and len(rows[0][1]) >= 4 * 6
    raw = (tmp_path / "sanad_mobile.vec").read_bytes()
    assert raw[:8] == mm.MAGIC
    cnt, dim = struct.unpack("<ii", raw[8:16])
    assert cnt == n
    scales = np.frombuffer(raw[16:16 + 4 * cnt], dtype="<f4")
    mat = np.frombuffer(raw[16 + 4 * cnt:], dtype=np.int8).reshape(cnt, dim).astype(np.float32) * scales[:, None]
    # row 0 = passage 1: same direction as the pack's float vector
    cid = con.execute("SELECT chunk_id FROM passage WHERE id=1").fetchone()[0]
    src = sqlite3.connect(pack_path)
    v = src.execute("SELECT vector FROM chunk_embedding WHERE chunk_id=?", (cid,)).fetchone()
    if v:
        f = np.frombuffer(v[0], dtype=np.float32)
        cos = float(mat[0] @ f / (np.linalg.norm(mat[0]) * np.linalg.norm(f)))
        assert cos > 0.999
    assert con.execute("SELECT COUNT(*) FROM stopword").fetchone()[0] > 50


def test_mobile_pack_keeps_every_dated_version(tmp_path, pack_path):
    """By default every version is kept with its dates, so the phone can answer for the date the user picks."""
    import make_mobile_pack as mm
    m_all = mm.build(Path(pack_path), tmp_path / "all")
    m_day = mm.build(Path(pack_path), tmp_path / "day", "2026-10-27")
    assert m_all["passages"] > m_day["passages"]  # the fixture has articles replaced on 2026-08-24
    con = sqlite3.connect(tmp_path / "all" / "sanad_mobile.db")
    assert con.execute("SELECT value FROM meta WHERE key='dated'").fetchone()[0] == "1"
    on = lambda d: con.execute("SELECT COUNT(*) FROM passage WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)", (d, d)).fetchone()[0]  # noqa: E731
    assert on("2026-10-27") == m_day["passages"]  # what the phone keeps for that date = the old one-date pack
    assert on("2000-06-01") != on("2026-10-27")
