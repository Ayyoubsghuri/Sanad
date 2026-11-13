"""Read-only access to the signed law pack: date-aware provision lookup, keyword search,
vector index, graph edges, rates, transitional rules, coverage."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from .schema_sql import AUTHORITY_RANK, TRUSTED_STATUSES

_TRUST_SQL = "(" + ",".join(f"'{s}'" for s in TRUSTED_STATUSES) + ")"
_FAR = 10**9



COMMON_NAMES = {
    "مدونة الأسرة": "LAW_70.03", "مدونة الاسرة": "LAW_70.03",
    "مجموعة القانون الجنائي": "DAHIR_1.59.413", "القانون الجنائي": "DAHIR_1.59.413",
    "قانون المسطرة الجنائية": "LAW_22.01", "المسطرة الجنائية": "LAW_22.01",
    "قانون المسطرة المدنية": "DAHIR_1.74.447", "المسطرة المدنية": "DAHIR_1.74.447",
    "قانون الالتزامات والعقود": "DAHIR_DOC-1913", "مدونة الشغل": "LAW_65.99", "مدونة التجارة": "LAW_15.95",
    # the abbreviations lawyers and exams use ("الفصل 440 من ق.م.م")
    "ق.م.م": "DAHIR_1.74.447", "ق م م": "DAHIR_1.74.447", "ق.ل.ع": "DAHIR_DOC-1913", "ق ل ع": "DAHIR_DOC-1913", "ظ.ل.ع": "DAHIR_DOC-1913",
    "ق.ج": "DAHIR_1.59.413", "ق ج": "DAHIR_1.59.413", "م.ج": "DAHIR_1.59.413", "ق.م.ج": "LAW_22.01", "ق م ج": "LAW_22.01", "ق.م.ج.م": "LAW_22.01",
    "م.أ": "LAW_70.03", "م.ا": "LAW_70.03", "م أ": "LAW_70.03", "م.ش": "LAW_65.99", "م ش": "LAW_65.99", "م.ت": "LAW_15.95", "م ت": "LAW_15.95",
    "مدونة الحقوق العينية": "LAW_39.08", "م.ح.ع": "LAW_39.08", "م ح ع": "LAW_39.08", "ظهير التحفيظ العقاري": "DAHIR_TF-1913",
    "مدونة السير": "LAW_52.05", "مدونة السير على الطرق": "LAW_52.05", "مدونة الجمارك": "DAHIR_1.77.339", "المدونة العامة للضرائب": "LAW_CGI-2024",
    "قانون التنظيم القضائي": "LAW_38.15", "التنظيم القضائي": "LAW_38.15", "قانون الشركات التجارية": "LAW_5.96", "قانون شركات المساهمة": "LAW_17.95",
}

_DEF_STOP = {"هذا القانون", "هذه المدونة", "هذا الظهير", "هذا المرسوم", "القانون", "المدونة", "ما يلي", "يلي", "هذا الباب", "هذا القسم", "هذا الفرع"}
_DEF_INTRO = re.compile(r"^\s*(?:يقصد|يراد|يعني|تعني)(?:\s+في\s+مدلول\s+\S+(?:\s+\S+)?)?\s+ب(?:عبارة\s+|كلمة\s+|لفظ\s+|مصطلح\s+)?\s*[«\"“]?\s*([^»\"”:،.؛)\n]{2,45}?)\s*(?=[»\"”]|\s+في\s+مدلول|\s+في\s+هذا|\s*:|،|\s+كل\s|\s+جميع\s|\s+الشخص\s|$)")
_DEF_LIST = re.compile(r"^\s*(?:يقصد|يراد)(?:\s+في\s+مدلول\s+\S+(?:\s+\S+)?)?\s+ب\s*[:،]?\s*(?:ما\s+يلي)?\s*:?\s*$", re.M)
_DEF_IS = re.compile(r"^\s*([^\s،.:«»\"0-9-]+(?:\s+[^\s،.:«»\"0-9-]+){0,3})\s+(?:هو|هي|هم)\s+\S")
_DEF_AGE = re.compile(r"^\s*(سن\s+\S+(?:\s+\S+)?)\s+(?:هو\s+|هي\s+|محدد\s+في\s+)?\d")
_DEF_ITEM = re.compile(r"(?m)^\s*(?:[-–•]|\d{1,2}\s*[-–.)])\s*[«\"“]?([^:«»\"“”\n]{2,40}?)[»\"”]?\s*:")


def definition_terms(head: str) -> list[str]:
    """Terms an article defines, read from its first lines.  Empty for an ordinary article."""
    out: list[str] = []
    first = head.split("\n", 1)[0]
    m = _DEF_INTRO.match(first)
    if m and m.group(1).strip():
        out.append(m.group(1))
    if m or _DEF_LIST.match(first):
        out += _DEF_ITEM.findall(head)  # "يراد في مدلول هذا القانون ب: - الفنان: ... - المهني: ..."
    for rx in (_DEF_IS, _DEF_AGE):
        m = rx.match(head)
        if m:
            out.append(m.group(1))
    clean = []
    for t in out:
        t = re.sub(r"^(?:ال)?(?:عبارة|كلمة|لفظ)\s+", "", t.strip(" \t-–:«»\"“”()."))
        if 4 <= len(t) <= 45 and t not in _DEF_STOP and len(t.split()) <= 5 and t not in clean:
            clean.append(t)
    return clean


# a code replaced by a new law under another number: a citation by the code's NAME ("المادة 486 من قانون المسطرة المدنية") on a date when
# only the new law is in force means the new law.  The old codes number their articles "الفصل", the new ones "المادة": "الفصل 440" stays old.
SUCCESSORS = {"DAHIR_1.74.447": "LAW_58.25"}


class PackError(RuntimeError):
    pass


_ORDINALS = {"الأولى": 1, "الاولى": 1, "الأول": 1, "الاول": 1, "الثانية": 2, "الثاني": 2, "الثالثة": 3, "الثالث": 3, "الرابعة": 4, "الرابع": 4,
             "الخامسة": 5, "الخامس": 5, "السادسة": 6, "السادس": 6, "السابعة": 7, "السابع": 7, "الثامنة": 8, "الثامن": 8, "التاسعة": 9, "التاسع": 9,
             "العاشرة": 10, "العاشر": 10}
_ARTICLE_MARK = re.compile(r"(?m)^[ \t]*(?:المادة|الفصل)[ \t]+(\d+|" + "|".join(sorted(_ORDINALS, key=len, reverse=True)) + r")[ \t]*$")


def article_part(body: str, number) -> str:
    """The part of a multi-article chunk that belongs to article `number`.  Markers are the article headings alone on their line
    ("المادة 24"); a reference inside a sentence ("المادة 4 أعلاه") is not one.  Unchanged when there is nothing to cut."""
    n = str(number or "").strip()
    if not n.isdigit() or not body:
        return body
    marks = [(m.start(), _ORDINALS[m.group(1)] if m.group(1) in _ORDINALS else int(m.group(1))) for m in _ARTICLE_MARK.finditer(body)]
    if len({k for _, k in marks}) < 2:
        return body
    for i, (pos, k) in enumerate(marks):
        if k == int(n):
            end = next((p2 for p2, k2 in marks[i + 1:] if k2 != k), len(body))
            return body[pos:end].strip() or body
    return body


@dataclass
class ChunkMeta:
    chunk_id: int
    pv_id: int
    lang: str
    edition: str
    paragraph_no: int | None
    body: str
    text: str
    provision_id: str
    instrument_id: str
    number: str
    path: str | None
    valid_from: str
    valid_to: str | None
    verification_status: str
    amended_by: str | None
    controlling_lang: str
    instrument_kind: str
    is_definition: bool
    is_transitional: bool

    @property
    def authority_rank(self) -> int:
        return AUTHORITY_RANK.get(self.instrument_kind, 9)


class VectorIndex:
    """Brute-force cosine search over one embedder's vectors, masked by as-of date and trust level."""

    def __init__(self, ids: np.ndarray, mat: np.ndarray, vf: np.ndarray, vt: np.ndarray, trusted: np.ndarray, embedder_id: str):
        self.ids, self.mat, self.vf, self.vt, self.trusted, self.embedder_id = ids, mat, vf, vt, trusted, embedder_id

    def search(self, qvec: np.ndarray, as_of: date, k: int, allow: np.ndarray | None = None) -> list[tuple[int, float]]:
        """`allow` = optional boolean array (one per vector) limiting the search, e.g. to laws and codes only."""
        if self.mat.shape[0] == 0:
            return []
        d = as_of.toordinal()
        mask = self.trusted & (self.vf <= d) & (self.vt > d)
        if allow is not None:
            mask = mask & allow
        if not mask.any():
            return []
        q = qvec.astype(np.float32)
        n = np.linalg.norm(q)
        if n == 0:
            return []
        scores = self.mat @ (q / n)
        scores = np.where(mask, scores, -np.inf)
        k = min(k, int(mask.sum()))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(int(self.ids[i]), float(scores[i])) for i in top if np.isfinite(scores[i])]


class LawPack:
    def __init__(self, path: Path):
        if not path.exists():
            raise PackError(f"law pack not found: {path}")
        self.path = path
        self._lock = threading.RLock()
        self._c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        self._c.row_factory = sqlite3.Row
        self.meta: dict[str, str] = {r["key"]: r["value"] for r in self._q("SELECT key,value FROM pack_meta")}
        self._indexes: dict[str, VectorIndex] = {}
        self._aliases: dict[str, str] | None = None

    # ---- plumbing ------------------------------------------------------------------------------
    def _q(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._c.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._c.execute(sql, params).fetchone()

    def close(self) -> None:
        with self._lock:
            self._c.close()

    @property
    def version(self) -> str:
        return self.meta.get("pack_version", "unknown")

    @property
    def built_at(self) -> str | None:
        return self.meta.get("built_at")

    def embedders(self) -> dict[str, dict]:
        return {r["embedder_id"]: dict(r) for r in self._q("SELECT * FROM embedder")}

    # ---- instruments ---------------------------------------------------------------------------------
    def instrument(self, instrument_id: str) -> dict | None:
        r = self._one("SELECT * FROM instrument WHERE instrument_id=?", (instrument_id,))
        return self._inst(r) if r else None

    @staticmethod
    def _inst(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["language_availability"] = json.loads(d["language_availability"]) if d.get("language_availability") else {}
        return d

    def instruments(self, kind: str | None = None, q: str | None = None, domain: str | None = None) -> list[dict]:
        sql, p = "SELECT * FROM instrument WHERE 1=1", []
        if kind:
            sql += " AND kind=?"; p.append(kind)
        if domain:
            sql += " AND domain=?"; p.append(domain)
        if q:
            sql += " AND (title_ar LIKE ? OR title_fr LIKE ? OR short_code LIKE ? OR number LIKE ?)"; p += [f"%{q}%"] * 4
        return [self._inst(r) for r in self._q(sql + " ORDER BY instrument_id", p)]

    def aliases(self) -> dict[str, str]:
        if self._aliases is None:
            self._aliases = {r["alias"]: r["instrument_id"] for r in self._q("SELECT alias,instrument_id FROM instrument_alias")}
            for r in self._q("SELECT instrument_id, short_code FROM instrument WHERE short_code IS NOT NULL"):
                self._aliases.setdefault(r["short_code"], r["instrument_id"])
            ids = self.instrument_ids()
            for name, iid in COMMON_NAMES.items():  # how the laws cite each other ("المادة 53 من مدونة الأسرة"), when the pack has no alias for it
                if iid in ids:
                    self._aliases.setdefault(name, iid)
        return self._aliases

    def instrument_ids(self) -> set[str]:
        if getattr(self, "_iids", None) is None:
            self._iids = {r["instrument_id"] for r in self._q("SELECT instrument_id FROM instrument")}
        return self._iids

    # ---- provisions & versions ---------------------------------------------------------------------------
    def find_provision(self, instrument_id: str, number: int, suffix: str = "") -> str | None:
        if suffix.startswith("-"):  # an added article "78-2" is stored under its full number
            r = self._one("SELECT provision_id FROM provision WHERE instrument_id=? AND number=?", (instrument_id, f"{number}{suffix}"))
            return r["provision_id"] if r else None
        r = self._one("SELECT provision_id FROM provision WHERE instrument_id=? AND number_int=? AND suffix=?", (instrument_id, number, suffix.lower()))
        if not r and not suffix:  # imported laws keep the number as text only
            r = self._one("SELECT provision_id FROM provision WHERE instrument_id=? AND number=?", (instrument_id, str(number)))
        return r["provision_id"] if r else None

    def provision(self, provision_id: str) -> dict | None:
        r = self._one("SELECT * FROM provision WHERE provision_id=?", (provision_id,))
        return dict(r) if r else None

    def provisions_of(self, instrument_id: str) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM provision WHERE instrument_id=? ORDER BY ordinal, number_int, suffix", (instrument_id,))]

    def versions(self, provision_id: str) -> list[dict]:
        rows = self._q(
            "SELECT pv.*, i.number AS amender_number, i.title_fr AS amender_title_fr, i.bo_number AS amender_bo FROM provision_version pv "
            "LEFT JOIN instrument i ON i.instrument_id=pv.amended_by WHERE provision_id=? ORDER BY valid_from",
            (provision_id,),
        )
        return [dict(r) for r in rows]

    def version_at(self, provision_id: str, as_of: date, trusted_only: bool = True) -> dict | None:
        sql = "SELECT * FROM provision_version WHERE provision_id=? AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)"
        if trusted_only:
            sql += f" AND verification_status IN {_TRUST_SQL}"
        r = self._one(sql + " ORDER BY valid_from DESC LIMIT 1", (provision_id, as_of.isoformat(), as_of.isoformat()))
        return dict(r) if r else None

    def version_before(self, provision_id: str, valid_from: str) -> dict | None:
        r = self._one(
            f"SELECT * FROM provision_version WHERE provision_id=? AND valid_from<? AND verification_status IN {_TRUST_SQL} ORDER BY valid_from DESC LIMIT 1",
            (provision_id, valid_from),
        )
        return dict(r) if r else None

    def version_boundaries(self, start: date, end: date) -> list[dict]:
        """Version changes with valid_from in (start, end]: used to detect date ambiguity."""
        rows = self._q(
            "SELECT provision_id, valid_from FROM provision_version WHERE valid_from>? AND valid_from<=? ORDER BY valid_from",
            (start.isoformat(), end.isoformat()),
        )
        return [dict(r) for r in rows]

    def texts(self, pv_id: int) -> dict[str, dict]:
        return {r["lang"]: {"text": r["text"], "edition": r["edition"]} for r in self._q("SELECT lang,edition,text FROM provision_text WHERE pv_id=?", (pv_id,))}

    def source_file(self, source_id: int) -> dict | None:
        r = self._one("SELECT * FROM source_file WHERE source_id=?", (source_id,))
        return dict(r) if r else None

    def provision_view(self, pv_id: int) -> dict | None:
        r = self._one(
            "SELECT pv.*, p.instrument_id, p.number, p.path, p.is_definition, p.is_transitional, i.kind AS instrument_kind, i.number AS instrument_number, "
            "i.short_code, i.title_ar, i.title_fr, i.bo_number, i.bo_date, i.status_flag, i.status_note, am.number AS amender_number, am.bo_number AS amender_bo "
            "FROM provision_version pv JOIN provision p ON p.provision_id=pv.provision_id JOIN instrument i ON i.instrument_id=p.instrument_id "
            "LEFT JOIN instrument am ON am.instrument_id=pv.amended_by WHERE pv.pv_id=?",
            (pv_id,),
        )
        if not r:
            return None
        d = dict(r)
        d["texts"] = self.texts(pv_id)
        src = self.source_file(d["source_id"])
        d["source"] = {"url": src["url"], "sha256": src["sha256"], "kind": src["kind"], "edition": src["edition"], "fetched_at": src["fetched_at"]} if src else None
        return d

    def article_location(self, provision_id: str, pv_id: int) -> dict | None:
        """{"pdf": path/uri of the source PDF, "page_start", "page_end", "bo_number"} for the article, None when the pack does not know."""
        try:
            r = self._one("SELECT pp.page_start,pp.page_end,sf.url,sf.sha256 FROM provision_page pp JOIN provision_version pv ON pv.source_id=pp.source_id AND pv.provision_id=pp.provision_id "
                          "JOIN source_file sf ON sf.source_id=pp.source_id WHERE pv.pv_id=? AND pp.provision_id=?", (pv_id, provision_id))
        except Exception:  # noqa: BLE001 - packs built before this table existed
            return None
        return dict(r) if r else None

    # ---- chunks & search -----------------------------------------------------------------------------------------
    _CHUNK_SQL = (
        "SELECT c.chunk_id,c.pv_id,c.lang,c.edition,c.paragraph_no,c.body,c.text,pv.provision_id,p.instrument_id,p.number,p.path,"
        "pv.valid_from,pv.valid_to,pv.verification_status,pv.amended_by,pv.controlling_lang,i.kind AS instrument_kind,p.is_definition,p.is_transitional "
        "FROM chunk c JOIN provision_version pv ON pv.pv_id=c.pv_id JOIN provision p ON p.provision_id=pv.provision_id JOIN instrument i ON i.instrument_id=p.instrument_id "
    )

    @staticmethod
    def _chunk(r: sqlite3.Row) -> ChunkMeta:
        d = dict(r)
        if d.get("paragraph_no") is None:  # one pipeline chunk may hold several articles (same text, same vector, one row each): keep THIS article's part
            d["body"] = article_part(d["body"], d.get("number"))
        d["is_definition"], d["is_transitional"] = bool(d["is_definition"]), bool(d["is_transitional"])
        return ChunkMeta(**d)

    def chunks(self, ids: list[int]) -> dict[int, ChunkMeta]:
        if not ids:
            return {}
        rows = self._q(self._CHUNK_SQL + f"WHERE c.chunk_id IN ({','.join('?' for _ in ids)})", ids)
        return {r["chunk_id"]: self._chunk(r) for r in rows}

    def chunks_for_pv(self, pv_id: int, official_only: bool = True) -> list[ChunkMeta]:
        sql = self._CHUNK_SQL + "WHERE c.pv_id=?" + (" AND c.edition='official'" if official_only else "") + " ORDER BY c.lang, c.paragraph_no"
        return [self._chunk(r) for r in self._q(sql, (pv_id,))]

    def instrument_chunk_ids(self, instrument_ids: list[str], as_of: date, limit: int = 300) -> list[int]:
        """Chunks of the given laws that are in force on `as_of` (a question that names a law is answered from that law)."""
        if not instrument_ids:
            return []
        ids = self.instrument_ids()  # with the later editions of the same law ("LAW_22.01" -> also "LAW_22.01_2025"): only the one in force matches
        instrument_ids = list(dict.fromkeys([*instrument_ids, *(i for x in instrument_ids for i in ids if i.startswith(x + "_"))]))
        ph = ",".join("?" for _ in instrument_ids)
        rows = self._q(
            "SELECT c.chunk_id FROM chunk c JOIN provision_version pv ON pv.pv_id=c.pv_id JOIN provision p ON p.provision_id=pv.provision_id "
            f"WHERE p.instrument_id IN ({ph}) AND c.edition='official' AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?) "
            f"AND pv.verification_status IN {_TRUST_SQL} ORDER BY c.chunk_id LIMIT ?",
            (*instrument_ids, as_of.isoformat(), as_of.isoformat(), limit))
        return [r["chunk_id"] for r in rows]

    def keyword_search(self, fts_query: str, as_of: date, limit: int, kinds: tuple[str, ...] | None = None) -> list[tuple[int, float]]:
        if not fts_query:
            return []
        kind_sql = ""
        if kinds:  # only passages of instruments of these kinds (laws and codes beside the flood of ministerial orders)
            kind_sql = ("JOIN provision pr ON pr.provision_id=pv.provision_id JOIN instrument ins ON ins.instrument_id=pr.instrument_id AND ins.kind IN ("
                        + ",".join("'" + k.replace("'", "") + "'" for k in kinds) + ") ")
        sql = (
            "SELECT c.chunk_id, bm25(chunk_fts) AS s FROM chunk_fts JOIN chunk c ON c.chunk_id=chunk_fts.rowid "
            "JOIN provision_version pv ON pv.pv_id=c.pv_id " + kind_sql + "WHERE chunk_fts MATCH ? AND c.edition='official' "
            f"AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?) AND pv.verification_status IN {_TRUST_SQL} ORDER BY s LIMIT ?"
        )
        try:
            rows = self._q(sql, (fts_query, as_of.isoformat(), as_of.isoformat(), limit))
        except sqlite3.OperationalError:
            return []
        return [(r["chunk_id"], -float(r["s"])) for r in rows]  # higher = better

    def kind_mask(self, embedder_id: str, kinds: tuple[str, ...]) -> np.ndarray | None:
        """Boolean array aligned with the vector index: True for passages of instruments of these kinds (cached)."""
        key = (embedder_id, kinds)
        cache = self.__dict__.setdefault("_kind_masks", {})
        if key not in cache:
            idx = self.vector_index(embedder_id)
            if idx is None:
                return None
            ph = ",".join("?" for _ in kinds)
            rows = self._q("SELECT c.chunk_id FROM chunk c JOIN provision_version pv ON pv.pv_id=c.pv_id JOIN provision p ON p.provision_id=pv.provision_id "
                           f"JOIN instrument i ON i.instrument_id=p.instrument_id WHERE i.kind IN ({ph})", tuple(kinds))
            cache[key] = np.isin(idx.ids, np.array([r["chunk_id"] for r in rows], dtype=np.int64))
        return cache[key]

    def vector_index(self, embedder_id: str) -> VectorIndex | None:
        if embedder_id in self._indexes:
            return self._indexes[embedder_id]
        emb = self.embedders().get(embedder_id)
        if not emb:
            return None
        rows = self._q(
            "SELECT ce.chunk_id, ce.vector, pv.valid_from, pv.valid_to, pv.verification_status FROM chunk_embedding ce "
            "JOIN chunk c ON c.chunk_id=ce.chunk_id JOIN provision_version pv ON pv.pv_id=c.pv_id WHERE ce.embedder_id=? AND c.edition='official'",
            (embedder_id,),
        )
        dim = emb["dim"]
        ids = np.array([r["chunk_id"] for r in rows], dtype=np.int64)
        mat = np.zeros((len(rows), dim), dtype=np.float32)
        for i, r in enumerate(rows):
            v = np.frombuffer(r["vector"], dtype=np.float32)
            n = np.linalg.norm(v)
            mat[i] = v / n if n else v
        vf = np.array([date.fromisoformat(r["valid_from"]).toordinal() for r in rows], dtype=np.int64)
        vt = np.array([date.fromisoformat(r["valid_to"]).toordinal() if r["valid_to"] else _FAR for r in rows], dtype=np.int64)
        tr = np.array([r["verification_status"] in TRUSTED_STATUSES for r in rows], dtype=bool)
        idx = VectorIndex(ids, mat, vf, vt, tr, embedder_id)
        self._indexes[embedder_id] = idx
        return idx

    # ---- graph, transitional rules, definitions --------------------------------------------------------------------
    def edges_from(self, kind: str, id_: str) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM edge WHERE from_kind=? AND from_id=?", (kind, id_))]

    def edges_to(self, kind: str, id_: str) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM edge WHERE to_kind=? AND to_id=?", (kind, id_))]

    def transitional_rules(self, instrument_id: str | None = None) -> list[dict]:
        if instrument_id:
            rows = self._q("SELECT * FROM transitional_rule WHERE instrument_id=? ORDER BY cutoff_date", (instrument_id,))
        else:
            rows = self._q("SELECT * FROM transitional_rule ORDER BY cutoff_date")
        return [dict(r) for r in rows]

    def definition_pvs(self, instrument_id: str, as_of: date) -> list[int]:
        rows = self._q(
            "SELECT pv.pv_id FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id WHERE p.instrument_id=? AND p.is_definition=1 "
            f"AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?) AND pv.verification_status IN {_TRUST_SQL}",
            (instrument_id, as_of.isoformat(), as_of.isoformat()),
        )
        return [r["pv_id"] for r in rows]

    def defined_terms(self, instrument_id: str, as_of: date) -> list[tuple[str, int]]:
        """(term, pv_id) for the articles of one law that define a term ("يراد ب...", "الطلاق هو ...", "سن الرشد القانوني 18 سنة"),
        so an article that only USES the term ("تستمر الحضانة إلى بلوغ سن الرشد القانوني") can bring its definition along."""
        cache = getattr(self, "_defs", None)
        if cache is None:
            cache = self._defs = {}
        if instrument_id not in cache:
            rows = self._q(
                "SELECT pv.pv_id, pv.valid_from, pv.valid_to, substr(pt.text, 1, 600) AS head FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id "
                f"JOIN provision_text pt ON pt.pv_id=pv.pv_id AND pt.lang='ar' WHERE p.instrument_id=? AND pv.verification_status IN {_TRUST_SQL}", (instrument_id,))
            found = []
            for r in rows:
                for t in definition_terms(r["head"] or ""):
                    found.append((t, r["pv_id"], r["valid_from"], r["valid_to"]))
            cache[instrument_id] = found
        d = as_of.isoformat()
        return [(t, pv) for t, pv, vf, vt in cache[instrument_id] if (vf or "") <= d and (not vt or vt > d)]

    def transitional_pvs(self, instrument_id: str, as_of: date) -> list[int]:
        rows = self._q(
            "SELECT pv.pv_id FROM provision p JOIN provision_version pv ON pv.provision_id=p.provision_id WHERE p.instrument_id=? AND p.is_transitional=1 "
            f"AND pv.valid_from<=? AND (pv.valid_to IS NULL OR pv.valid_to>?) AND pv.verification_status IN {_TRUST_SQL}",
            (instrument_id, as_of.isoformat(), as_of.isoformat()),
        )
        return [r["pv_id"] for r in rows]

    def first_chunk_ids(self, pv_id: int) -> list[int]:
        return [r["chunk_id"] for r in self._q("SELECT chunk_id FROM chunk WHERE pv_id=? AND edition='official' ORDER BY (lang='ar') DESC, paragraph_no", (pv_id,))]

    # ---- rates, deadline rules, holidays --------------------------------------------------------------------------------
    def rate_at(self, key: str, on: date) -> dict | None:
        r = self._one(
            "SELECT * FROM rate_table WHERE key=? AND valid_from<=? AND (valid_to IS NULL OR valid_to>?) ORDER BY valid_from DESC LIMIT 1",
            (key, on.isoformat(), on.isoformat()),
        )
        return self._rate(r) if r else None

    def rate_rows(self, key: str) -> list[dict]:
        return [self._rate(r) for r in self._q("SELECT * FROM rate_table WHERE key=? ORDER BY valid_from", (key,))]

    @staticmethod
    def _rate(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["extra"] = json.loads(d.pop("extra_json")) if d.get("extra_json") else None
        return d

    def rate_keys(self) -> list[str]:
        return [r["key"] for r in self._q("SELECT DISTINCT key FROM rate_table ORDER BY key")]

    def deadline_rules(self, kind: str, case_type: str) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM deadline_rule WHERE kind=? AND case_type=?", (kind, case_type))]

    def all_deadline_rules(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT kind, case_type, court, regime, trigger, amount, unit, valid_from, valid_to, provision_id, note FROM deadline_rule ORDER BY kind, case_type, valid_from")]

    def holidays(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self._q("SELECT * FROM holiday"):
            out.setdefault(r["date"], []).append(dict(r))
        return out

    # ---- decisions, bills, concordance ---------------------------------------------------------------------------------------
    def decisions_for(self, provision_id: str) -> list[dict]:
        rows = self._q(
            "SELECT d.decision_id,d.court,d.decision_date,d.number,d.chamber,dp.pv_id FROM decision d JOIN decision_provision dp ON dp.decision_id=d.decision_id "
            "WHERE dp.provision_id=? ORDER BY d.decision_date DESC",
            (provision_id,),
        )
        return [dict(r) for r in rows]

    def decision(self, decision_id: str) -> dict | None:
        r = self._one("SELECT * FROM decision WHERE decision_id=?", (decision_id,))
        return dict(r) if r else None

    def search_decisions(self, q: str, limit: int = 20) -> list[dict]:
        rows = self._q("SELECT decision_id,court,decision_date,number,chamber, substr(full_text,1,300) AS excerpt FROM decision WHERE full_text LIKE ? LIMIT ?", (f"%{q}%", limit))
        return [dict(r) for r in rows]

    def pending_bills(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM pending_bill ORDER BY bill_no")]

    def concordance(self, old_instrument: str | None = None, new_instrument: str | None = None) -> list[dict]:
        sql = (
            "SELECT c.*, po.instrument_id AS old_instrument, pn.instrument_id AS new_instrument, po.number AS old_number, pn.number AS new_number "
            "FROM concordance c JOIN provision po ON po.provision_id=c.old_provision_id JOIN provision pn ON pn.provision_id=c.new_provision_id WHERE 1=1"
        )
        p: list[Any] = []
        if old_instrument:
            sql += " AND po.instrument_id=?"; p.append(old_instrument)
        if new_instrument:
            sql += " AND pn.instrument_id=?"; p.append(new_instrument)
        return [dict(r) for r in self._q(sql + " ORDER BY po.ordinal", p)]

    # ---- reports -------------------------------------------------------------------------------------------------------------------
    def trust_stats(self) -> dict[str, Any]:
        rows = self._q("SELECT verification_status AS s, COUNT(*) AS n FROM provision_version WHERE valid_to IS NULL GROUP BY s")
        counts = {r["s"]: r["n"] for r in rows}
        total = sum(counts.values()) or 1
        return {"current_versions": counts, "share": {k: round(v / total, 4) for k, v in counts.items()}, "total_current": sum(counts.values())}

    def coverage(self) -> list[dict]:
        rows = self._q(
            "SELECT i.instrument_id,i.kind,i.number,i.short_code,i.title_fr,i.consolidated_text_available,i.language_availability,i.implementation_status,"
            "i.implementation_checked_on,i.official_article_count,i.status_flag,(SELECT COUNT(*) FROM provision p WHERE p.instrument_id=i.instrument_id) AS provisions "
            "FROM instrument i ORDER BY i.instrument_id"
        )
        out = []
        for r in rows:
            d = dict(r)
            d["language_availability"] = json.loads(d["language_availability"]) if d["language_availability"] else {}
            out.append(d)
        return out

    def provision_checksums(self) -> dict[tuple[str, str], str]:
        """(provision_id, valid_from) -> checksum, used to compute 'changed since' between packs."""
        return {(r["provision_id"], r["valid_from"]): r["checksum"] for r in self._q("SELECT provision_id,valid_from,checksum FROM provision_version")}
