"""Court of Cassation rulings (rulings.db, built by the publisher's importer) and search over them.

The database is optional: without it the tools still work from the law alone and say so. It is looked for at
<data_dir>/rulings/rulings.db (LEGALRAG_RULINGS_PATH overrides)."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..text import stopwords

OUTCOME_AR = {"cassation": "نقض", "partial_cassation": "نقض جزئي", "rejected": "رفض الطلب", "inadmissible": "عدم القبول",
              "reversed": "إلغاء الحكم المستأنف", "affirmed": "تأييد الحكم المستأنف", "rectified": "إصلاح خطأ مادي", "lapsed": "سقوط الطلب", "withdrawn": "تنازل / تشطيب", "other": "أخرى"}
CHAMBERS = ("civil", "family", "commercial", "administrative", "social", "criminal", "real_estate")
_WORD = re.compile(r"[ء-ي]{3,}|[A-Za-zÀ-ÿ]{4,}")
_PREFIX = re.compile(r"^(?:وال|بال|فال|كال|لل|ال|و|ف|ب)(?=[ء-ي]{3,})")
_EXTRA_STOP = {"الذي", "التي", "الذين", "هذا", "هذه", "ذلك", "تلك", "على", "إلى", "عن", "في", "من", "مع", "بعد", "قبل", "حيث", "وأن", "أن", "إن",
               "كان", "كانت", "يكون", "لكن", "ولكن", "أيضا", "عند", "عندما", "فقط", "جدا", "كل", "بين", "أنا", "أنه", "أنها", "لقد", "قد", "لم", "لا",
               "سيدي", "شخص", "يوم", "سنة", "تاريخ", "بتاريخ", "درهم", "مبلغ"}


def _norm(w: str) -> str:
    w = re.sub("[ً-ْـ]", "", w)
    return w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")


class RulingsStore:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        con = self._con()
        con.execute("SELECT 1 FROM ruling LIMIT 1")
        self.has_fts = bool(con.execute("SELECT name FROM sqlite_master WHERE name='ruling_fts'").fetchone())
        cols = {r[1] for r in con.execute("PRAGMA table_info(ruling)")}
        self.has_case_type = "case_type" in cols

    def _con(self) -> sqlite3.Connection:
        c = getattr(self._local, "con", None)
        if c is None:
            c = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, check_same_thread=False)
            c.row_factory = sqlite3.Row
            self._local.con = c
        return c

    # ------------------------------------------------------------------------------------------------ stats
    def stats(self) -> dict[str, Any]:
        con = self._con()
        total = con.execute("SELECT COUNT(*) FROM ruling").fetchone()[0]
        by_outcome = dict(con.execute("SELECT COALESCE(outcome,''), COUNT(*) FROM ruling GROUP BY 1").fetchall())
        by_chamber = dict(con.execute("SELECT COALESCE(chamber,''), COUNT(*) FROM ruling GROUP BY 1").fetchall())
        span = con.execute("SELECT MIN(decision_date), MAX(decision_date) FROM ruling WHERE decision_date<>''").fetchone()
        updated = con.execute("SELECT value FROM meta WHERE key='updated'").fetchone() if self._has_meta() else None
        return {"total": total, "by_outcome": by_outcome, "by_chamber": by_chamber, "from": span[0], "to": span[1],
                "updated": updated[0] if updated else None}

    def _has_meta(self) -> bool:
        return bool(self._con().execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone())

    # ------------------------------------------------------------------------------------------------ search
    @staticmethod
    def query_terms(text: str, limit: int = 14) -> list[str]:
        seen, out = set(), []
        for w in _WORD.findall(text or ""):
            if w in _EXTRA_STOP or w in stopwords.ALL:
                continue
            base = _PREFIX.sub("", w)
            if len(base) < 3 or base in seen:
                continue
            seen.add(base)
            out.append(base)
        out.sort(key=len, reverse=True)       # longer words are more specific
        return out[:limit]

    def search(self, text: str, k: int = 8, chamber: str | None = None, since: str | None = None,
               outcome: str | None = None) -> list[dict[str, Any]]:
        terms = self.query_terms(text)
        if not terms:
            return []
        con = self._con()
        where, params = [], []
        if chamber:
            where.append("r.chamber=?"); params.append(chamber)
        if since:
            where.append("r.decision_date>=?"); params.append(since)
        if outcome:
            where.append("r.outcome=?"); params.append(outcome)
        extra = (" AND " + " AND ".join(where)) if where else ""
        rows: list[sqlite3.Row] = []
        if self.has_fts:
            # each word as written, with the article "ال" and the common prefixes, all as prefix matches
            alts = []
            for t in terms:
                forms = {t, "ال" + t, "وال" + t, "بال" + t, "لل" + t}
                alts.append("(" + " OR ".join(f'"{f}"*' for f in sorted(forms)) + ")")
            fts_q = " OR ".join(alts)
            sql = (f"SELECT r.*, bm25(ruling_fts, 0, 4.0, 3.0, 1.0, 2.0, 1.0) AS score FROM ruling_fts f JOIN ruling r ON r.ruling_id=f.ruling_id "
                   f"WHERE ruling_fts MATCH ?{extra} ORDER BY score LIMIT ?")
            try:
                rows = con.execute(sql, (fts_q, *params, k * 3)).fetchall()
            except sqlite3.OperationalError:
                rows = []
        if not rows:   # no FTS table (or a query FTS refuses): plain LIKE on the subject lines
            like = " OR ".join("(r.keywords LIKE ? OR r.principle LIKE ?)" for _ in terms[:6])
            p2 = [x for t in terms[:6] for x in (f"%{t}%", f"%{t}%")]
            rows = con.execute(f"SELECT r.*, 0 AS score FROM ruling r WHERE ({like}){extra} LIMIT ?", (*p2, *params, k * 3)).fetchall()
        # re-rank: how many of the case's words the ruling's subject/principle contain (BM25 over long facts is noisy)
        nt = [_norm(t) for t in terms]
        scored = []
        for r in rows:
            head = _norm(f"{r['keywords'] or ''} {r['principle'] or ''}")
            body = _norm((r["facts"] or "")[:3000])
            head_hits = sum(1 for t in nt if t in head)
            hits = 2 * head_hits + sum(1 for t in nt if t in body)
            # a ruling must share the case's subject, not just common words: one subject word, or several in its facts
            if head_hits == 0 and hits < 3:
                continue
            scored.append((hits - 0.01 * float(r["score"] or 0), r))
        scored.sort(key=lambda x: -x[0])
        return [self.card(r) for _, r in scored[:k]]

    def get(self, ruling_id: str) -> dict[str, Any] | None:
        r = self._con().execute("SELECT * FROM ruling WHERE ruling_id=?", (ruling_id,)).fetchone()
        if not r:
            return None
        d = self.card(r, full=True)
        d["full_text"] = r["full_text"]
        return d

    def card(self, r: sqlite3.Row, full: bool = False) -> dict[str, Any]:
        grounds = json.loads(r["grounds_json"] or "[]")
        cut = (lambda s, n: s if full or len(s or "") <= n else (s or "")[:n] + "…")
        return {
            "ruling_id": r["ruling_id"], "number": r["number"], "date": r["decision_date"], "file_number": r["file_number"],
            "chamber": r["chamber"], "case_type": r["case_type"] if self.has_case_type else None,
            "outcome": r["outcome"], "outcome_ar": OUTCOME_AR.get(r["outcome"] or "", ""),
            "petitioner_won": None if r["petitioner_won"] is None else bool(r["petitioner_won"]),
            "keywords": r["keywords"], "principle": cut(r["principle"] or "", 900), "facts": cut(r["facts"] or "", 1200),
            "grounds": [{"ground": cut(g.get("ground", ""), 700), "answer": cut(g.get("answer", ""), 900), "accepted": g.get("accepted")} for g in grounds[:6]],
            "verdict": cut(r["verdict"] or "", 500), "quality": r["text_quality"], "ocr": bool(r["ocr"]),
            "source_url": f"https://pub-ecd37824be8e4b1da4aa7297a0ed1619.r2.dev/juriscassation_documents/{r['ruling_id']}.pdf"
            if str(r["ruling_id"]).isdigit() else None,
        }


def related_for_answer(store: RulingsStore, text: str, k: int = 3, pool: int = 20) -> dict[str, Any] | None:
    """Court of Cassation rulings on the same subject as a chat question, shown under the answer, apart from the law.
    by_outcome counts the outcomes among the most similar rulings found (at most `pool`)."""
    found = store.search(text, k=pool)
    if not found:
        return None
    by_outcome: dict[str, int] = {}
    for r in found:
        o = r.get("outcome") or "unknown"
        by_outcome[o] = by_outcome.get(o, 0) + 1
    items = [{key: r.get(key) for key in ("ruling_id", "number", "date", "file_number", "chamber", "outcome", "outcome_ar",
                                           "keywords", "source_url")}
             | {"principle": (r.get("principle") or "")[:400] + ("…" if len(r.get("principle") or "") > 400 else "")}
             for r in found[:k]]
    return {"similar": len(found), "by_outcome": by_outcome, "items": items}


_CACHE: dict[str, Any] = {}


def rulings_path(data_dir: Path) -> Path:
    """LEGALRAG_RULINGS_PATH, else the version the app downloaded (rulings/current.txt names it), else rulings/rulings.db
    (copied by hand). Each download gets its own file name, so Windows never has to replace a file that is open."""
    env = os.environ.get("LEGALRAG_RULINGS_PATH")
    if env:
        return Path(env)
    folder = data_dir / "rulings"
    cur = folder / "current.txt"
    if cur.exists():
        name = cur.read_text(encoding="utf-8").strip()
        if name and "/" not in name and "\\" not in name and (folder / name).exists():
            return folder / name
    return folder / "rulings.db"


def installed_version(data_dir: Path) -> str | None:
    p = rulings_path(data_dir)
    if not p.exists():
        return None
    m = re.match(r"^rulings-(.+)\.db$", p.name)
    if m:                       # downloaded by the app: the version is in the name
        return m.group(1)
    try:
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        finally:
            con.close()
        return row[0] if row else "local"
    except sqlite3.Error:
        return "local"


def open_store(data_dir: Path) -> RulingsStore | None:
    p = rulings_path(data_dir)
    if not p.exists():
        return None
    key = f"{p}:{p.stat().st_mtime_ns}"
    if _CACHE.get("key") != key:
        try:
            _CACHE.update(key=key, store=RulingsStore(p))
        except sqlite3.Error:
            _CACHE.update(key=key, store=None)
    return _CACHE.get("store")
