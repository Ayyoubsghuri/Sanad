"""Law tools that work on the pack alone (no language model):

  * old -> new article finder: where did article N of an old or replaced text go (1974 civil procedure code -> Law 58.25, an old edition ->
    the consolidated one).  Stored vectors of both articles + word overlap; every result is labelled "derived" with its score.
  * article history: every text an article had, across the editions of the law that the pack holds (base text + consolidated editions),
    with a word diff between consecutive texts, the amending laws and the version in force on a date.

Editions: a newer consolidated text is installed as its own instrument "<id>_<suffix>" (LAW_15.95 -> LAW_15.95_2026) and the old one is
retired on the day the new one starts.  Here they are read as ONE law (its family)."""
from __future__ import annotations

import math
import re
import threading
from datetime import date
from typing import Any

import numpy as np

from ..store.lawpack import SUCCESSORS, LawPack
from ..text.arabic import keyword_text, normalize
from ..text.citations import CitationRef, parse_citations
from .status import diff_texts


class ToolError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **self.extra}


# ------------------------------------------------------------------------------------------------ families of editions
def base_id(pack: LawPack, iid: str) -> str:
    """LAW_15.95_2026 -> LAW_15.95 when the pack holds LAW_15.95 (an edition installed beside it); otherwise the id itself."""
    ids = pack.instrument_ids()
    parts = iid.split("_")
    for n in range(len(parts) - 1, 1, -1):
        cand = "_".join(parts[:n])
        if cand in ids:
            return cand
    return iid


def family(pack: LawPack, iid: str) -> list[str]:
    """The base text and its editions, oldest first (by the first day any of its article versions starts)."""
    base = base_id(pack, iid)
    members = [i for i in pack.instrument_ids() if i == base or i.startswith(base + "_")]
    first: dict[str, str] = {}
    for m in members:
        r = pack._one("SELECT MIN(pv.valid_from) AS f FROM provision_version pv JOIN provision p ON p.provision_id=pv.provision_id WHERE p.instrument_id=?", (m,))
        first[m] = (r["f"] if r and r["f"] else (pack.instrument(m) or {}).get("effective_date") or "9999")
    return sorted(members, key=lambda m: (first[m], m))


def successor_of(pack: LawPack, iid: str) -> str | None:
    """The law that replaced this one: a known successor (1974 code -> 58.25), else the newest edition of the same law."""
    base = base_id(pack, iid)
    if base in SUCCESSORS and SUCCESSORS[base] in pack.instrument_ids():
        fam = family(pack, SUCCESSORS[base])
        return fam[-1] if fam else SUCCESSORS[base]
    fam = family(pack, iid)
    newer = fam[fam.index(iid) + 1:] if iid in fam else []
    return newer[-1] if newer else None


# ------------------------------------------------------------------------------------------------ resolving the article asked about
_ART_TXT = re.compile(r"^\s*(\d{1,4})\s*((?:[-–]\s*\d{1,3}){0,2})\s*(bis|ter|quater|مكرر|ثالثا|رابعا)?\s*$", re.I)
_SFX = {"bis": "bis", "ter": "ter", "quater": "quater", "مكرر": "bis", "ثالثا": "ter", "رابعا": "quater"}


def parse_article(article: str) -> tuple[int, str]:
    """"440" -> (440, ""), "78-2" -> (78, "-2"), "46 مكرر" -> (46, "bis")."""
    m = _ART_TXT.match(normalize(article or "").replace("–", "-"))
    if not m:
        raise ToolError(422, "bad_article", f"article number not understood: {article!r} (examples: 440, 78-2, 46 مكرر)")
    dash = re.sub(r"\s+", "", m.group(2) or "")
    return int(m.group(1)), dash or _SFX.get((m.group(3) or "").lower(), "")


def _find_in_family(pack: LawPack, iid: str, number: int, suffix: str) -> tuple[str, str] | None:
    """(instrument_id, provision_id): the named text first, then its other editions (newest first)."""
    for m in [iid, *reversed(family(pack, iid))]:
        pid = pack.find_provision(m, number, suffix)
        if pid:
            return m, pid
    return None


def resolve(pack: LawPack, ref: str | None = None, instrument: str | None = None, article: str | None = None,
            exact_instrument: bool = False) -> dict[str, Any]:
    """-> {instrument_id, provision_id, number, suffix, label}.  `ref` is free text ("الفصل 440 من ق.م.م", "article 30 CPC");
    or `instrument` + `article`.  With exact_instrument the article must be in that very instrument (no edition fallback)."""
    if instrument:
        if instrument not in pack.instrument_ids():
            raise ToolError(404, "unknown_law", f"law not in the pack: {instrument}")
        number, suffix = parse_article(article or "")
        refs = [CitationRef(instrument, number, suffix, article or "", 0, 0)]
    elif ref:
        refs = [r for r in parse_citations(ref, pack.aliases(), pack.instrument_ids())]
        if not refs:
            raise ToolError(422, "no_article", "no article number found in the reference (example: الفصل 440 من قانون المسطرة المدنية)")
        if not any(r.instrument_id for r in refs):
            raise ToolError(422, "which_law", "the article was found but not the law: add the law's name or number", article=refs[0].label)
        refs = [r for r in refs if r.instrument_id]
    else:
        raise ToolError(422, "missing", "give `ref`, or `instrument` and `article`")
    r = refs[0]
    hit = (lambda: (r.instrument_id, pack.find_provision(r.instrument_id, r.number, r.suffix)))() if exact_instrument else _find_in_family(pack, r.instrument_id, r.number, r.suffix)
    if not hit or not hit[1]:
        raise ToolError(404, "article_not_in_pack", f"article {r.label} is not in {r.instrument_id} (or its editions) in your law pack",
                        instrument_id=r.instrument_id, article=r.label)
    return {"instrument_id": hit[0], "provision_id": hit[1], "number": r.number, "suffix": r.suffix, "label": r.label}


# ------------------------------------------------------------------------------------------------ article texts and vectors
def _versions(pack: LawPack, pid: str) -> list[dict]:
    return [v for v in pack.versions(pid)]


def _text(pack: LawPack, pv_id: int, lang: str = "ar") -> str:
    t = pack.texts(pv_id)
    return (t.get(lang) or t.get("ar") or next(iter(t.values()), {"text": ""}))["text"] or ""


def _version_for(pack: LawPack, pid: str, as_of: date | None) -> dict | None:
    """The version in force on as_of; else the last version that started before it (an ended article: its last text); else the first."""
    vs = _versions(pack, pid)
    if not vs:
        return None
    if as_of:
        d = as_of.isoformat()
        cur = [v for v in vs if v["valid_from"] <= d and (not v["valid_to"] or v["valid_to"] > d)]
        if cur:
            return cur[-1]
        before = [v for v in vs if v["valid_from"] <= d]
        if before:
            return before[-1]
        return vs[0]
    return vs[-1]


def _embedder_id(pack: LawPack) -> str | None:
    embs = list(pack.embedders())
    real = [e for e in embs if not e.startswith("hash")]
    return (real or embs or [None])[0]


def _pv_vectors(pack: LawPack, pv_ids: list[int], emb: str | None) -> dict[int, np.ndarray]:
    """One unit vector per article version: the mean of its Arabic official chunks' stored vectors (no model is run)."""
    if not emb or not pv_ids:
        return {}
    out: dict[int, list[np.ndarray]] = {}
    for i in range(0, len(pv_ids), 900):
        part = pv_ids[i:i + 900]
        rows = pack._q(f"SELECT c.pv_id, ce.vector FROM chunk c JOIN chunk_embedding ce ON ce.chunk_id=c.chunk_id WHERE ce.embedder_id=? AND c.edition='official' "
                       f"AND c.pv_id IN ({','.join('?' * len(part))})", (emb, *part))
        for r in rows:
            out.setdefault(r["pv_id"], []).append(np.frombuffer(r["vector"], dtype=np.float32))
    res: dict[int, np.ndarray] = {}
    for pv, vs in out.items():
        m = np.mean(np.stack(vs), axis=0)
        n = float(np.linalg.norm(m))
        if n:
            res[pv] = m / n
    return res


_STOPSTEMS = set(keyword_text("في من على إلى عن أن او أو التي الذي هذا هذه ذلك كل بعد قبل عند مع غير بين لا ما لم قد كما وفق حسب حيث إذا اذا ثم هو هي "
                              "المادة الفصل الفقرة القانون هذا المقتضيات أحكام احكام بها به له لها").split())


def word_set(text: str) -> set[str]:
    """Light stems (the search index's own form) without common words; numbers kept: "10 أيام" and "30 يوما" are strong evidence."""
    return {w for w in keyword_text(text).split() if (len(w) >= 3 or w.isdigit()) and w not in _STOPSTEMS}


def _overlap(a: set[str], b: set[str]) -> float:
    return len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0


def _law_rows(pack: LawPack, iids: list[str], as_of: date | None) -> list[dict]:
    """Every article of these instruments with the version to compare: the one in force on as_of, else its latest."""
    out = []
    for iid in iids:
        for p in pack.provisions_of(iid):
            v = _version_for(pack, p["provision_id"], as_of)
            if v:
                out.append({"provision_id": p["provision_id"], "instrument_id": iid, "number": p["number"], "path": p.get("path"), "pv_id": v["pv_id"],
                            "valid_from": v["valid_from"], "valid_to": v["valid_to"], "trust": v["verification_status"]})
    # the same article in two editions: keep the one the date selects (the newest edition that has it)
    best: dict[str, dict] = {}
    for r in out:
        k = r["number"]
        d = (as_of or date.max).isoformat()
        in_force = r["valid_from"] <= d and (not r["valid_to"] or r["valid_to"] > d)
        prev = best.get(k)
        if prev is None or (in_force, r["valid_from"]) > (prev["_in_force"], prev["valid_from"]):
            best[k] = {**r, "_in_force": in_force}
    return list(best.values())


def _confidence(s1: float, s2: float) -> str:
    if s1 >= 0.55 and s1 - s2 >= 0.06:
        return "high"
    if s1 >= 0.40:
        return "medium"
    return "low"


def _weights(emb: str | None) -> tuple[float, float]:
    """(vector, words): the hashing embedder of test packs is a word-gram bag already, a real model (bge-m3) reads meaning."""
    if not emb:
        return 0.0, 1.0
    return (0.35, 0.65) if emb.startswith("hash") else (0.6, 0.4)


# ------------------------------------------------------------------------------------------------ old -> new finder
def find_new_article(pack: LawPack, ref: str | None = None, instrument: str | None = None, article: str | None = None, target: str | None = None,
                     as_of: date | None = None, k: int = 5, lang: str = "ar") -> dict[str, Any]:
    old = resolve(pack, ref, instrument, article, exact_instrument=bool(instrument))
    old_v = _version_for(pack, old["provision_id"], None)  # the article's last text
    old_text = _text(pack, old_v["pv_id"], lang) if old_v else ""
    if target and target not in pack.instrument_ids():
        raise ToolError(404, "unknown_law", f"target law not in the pack: {target}")
    tgt = target or successor_of(pack, old["instrument_id"])
    if not tgt:
        raise ToolError(404, "no_newer_text", "the pack holds no newer text for this law: give `target` (the new law's id)", instrument_id=old["instrument_id"])
    same_law = base_id(pack, tgt) == base_id(pack, old["instrument_id"])
    tgt_ids = family(pack, tgt) if not same_law else [i for i in family(pack, tgt) if i != old["instrument_id"]]
    rows = _law_rows(pack, tgt_ids, as_of)
    if not rows:
        raise ToolError(404, "target_empty", f"{tgt} has no article text in your pack")
    emb = _embedder_id(pack)
    vecs = _pv_vectors(pack, [old_v["pv_id"], *[r["pv_id"] for r in rows]], emb)
    ov = vecs.get(old_v["pv_id"])
    ow = word_set(old_text)
    wv, ww = _weights(emb if ov is not None else None)
    texts = {r["pv_id"]: _text(pack, r["pv_id"], lang) for r in rows}
    scored = []
    for r in rows:
        vs = float(ov @ vecs[r["pv_id"]]) if ov is not None and r["pv_id"] in vecs else 0.0
        ws = _overlap(ow, word_set(texts[r["pv_id"]]))
        s = wv * max(vs, 0.0) + ww * ws if (ov is not None and r["pv_id"] in vecs) else ws
        same_number = str(r["number"]) == f"{old['number']}{old['suffix']}" or str(r["number"]) == str(old["number"]) and not old["suffix"]
        if same_law and same_number:
            s += 0.15  # a new edition of the same law keeps its numbering: the same number is the natural continuation
        scored.append((s, vs, ws, same_number, r))
    scored.sort(key=lambda x: -x[0])
    top = scored[:max(1, min(k, 20))]
    s1, s2 = top[0][0], (top[1][0] if len(top) > 1 else 0.0)
    best_text = texts[top[0][4]["pv_id"]]
    tinst = pack.instrument(tgt) or {}
    return {
        "label": "derived",
        "method": f"stored article vectors ({emb or 'none'}) + shared words" + (" + same number in a new edition of the same law" if same_law else ""),
        "old": {**old, "text": old_text, "valid_from": old_v and old_v["valid_from"], "valid_to": old_v and old_v["valid_to"],
                "law": (pack.instrument(old["instrument_id"]) or {}).get("title_ar")},
        "target": {"instrument_id": tgt, "title_ar": tinst.get("title_ar"), "title_fr": tinst.get("title_fr"), "same_law_new_edition": same_law, "searched": tgt_ids},
        "confidence": _confidence(s1, s2),
        "matches": [{"provision_id": r["provision_id"], "instrument_id": r["instrument_id"], "number": r["number"], "path": r["path"], "score": round(s, 4),
                     "vector_similarity": round(vs, 4), "word_overlap": round(ws, 4), "same_number": same_number, "valid_from": r["valid_from"], "valid_to": r["valid_to"],
                     "trust": r["trust"], "text": texts[r["pv_id"]]} for s, vs, ws, same_number, r in top],
        "diff_with_best": diff_texts(old_text, best_text),
        "note": "Derived by comparing texts, not an official table: read both articles before relying on it. Low confidence often means the rule was split, merged or dropped.",
    }


_TABLE_CACHE: dict[tuple, dict] = {}
_TABLE_LOCK = threading.Lock()


def concordance_table(pack: LawPack, old_instrument: str, target: str | None = None, as_of: date | None = None, lang: str = "ar") -> dict[str, Any]:
    """Every article of the old text -> its best match in the new one (and the new articles nothing maps to).  Cached per pack version."""
    if old_instrument not in pack.instrument_ids():
        raise ToolError(404, "unknown_law", f"law not in the pack: {old_instrument}")
    tgt = target or successor_of(pack, old_instrument)
    if not tgt:
        raise ToolError(404, "no_newer_text", "the pack holds no newer text for this law: give `target`")
    key = (pack.version, str(pack.path), old_instrument, tgt, as_of, lang)
    with _TABLE_LOCK:
        if key in _TABLE_CACHE:
            return _TABLE_CACHE[key]
    same_law = base_id(pack, tgt) == base_id(pack, old_instrument)
    old_rows = []
    for p in pack.provisions_of(old_instrument):
        v = _version_for(pack, p["provision_id"], None)
        if v:
            old_rows.append({"provision_id": p["provision_id"], "number": p["number"], "pv_id": v["pv_id"]})
    tgt_ids = family(pack, tgt) if not same_law else [i for i in family(pack, tgt) if i != old_instrument]
    new_rows = _law_rows(pack, tgt_ids, as_of)
    if not old_rows or not new_rows:
        raise ToolError(404, "empty", "one of the two texts has no articles in your pack")
    emb = _embedder_id(pack)
    vecs = _pv_vectors(pack, [r["pv_id"] for r in old_rows + new_rows], emb)
    wv, ww = _weights(emb)
    dim = next(iter(vecs.values())).shape[0] if vecs else 0
    O = np.stack([vecs.get(r["pv_id"], np.zeros(dim, np.float32)) for r in old_rows]) if dim else None
    N = np.stack([vecs.get(r["pv_id"], np.zeros(dim, np.float32)) for r in new_rows]) if dim else None
    sims = (O @ N.T) if dim else np.zeros((len(old_rows), len(new_rows)), np.float32)
    nw = [word_set(_text(pack, r["pv_id"], lang)) for r in new_rows]
    used: set[str] = set()
    out_rows = []
    for i, o in enumerate(old_rows):
        ow = word_set(_text(pack, o["pv_id"], lang))
        # words over every new article would be slow on two big codes: the vectors pick 12 candidates, words decide among them
        cand_idx = list(np.argsort(-sims[i])[:12]) if dim else list(range(len(new_rows)))
        if same_law:
            cand_idx += [j for j, r in enumerate(new_rows) if str(r["number"]) == str(o["number"]) and j not in cand_idx]
        best = []
        for j in cand_idx:
            ws = _overlap(ow, nw[j])
            s = (wv * max(float(sims[i, j]), 0.0) + ww * ws) if dim else ws
            if same_law and str(new_rows[j]["number"]) == str(o["number"]):
                s += 0.15
            best.append((s, j))
        best.sort(reverse=True)
        s1, j1 = best[0]
        s2 = best[1][0] if len(best) > 1 else 0.0
        conf = _confidence(s1, s2)
        if conf != "low":
            used.add(new_rows[j1]["provision_id"])
        out_rows.append({"old_number": o["number"], "old_provision_id": o["provision_id"], "new_number": new_rows[j1]["number"],
                         "new_provision_id": new_rows[j1]["provision_id"], "new_instrument_id": new_rows[j1]["instrument_id"], "score": round(s1, 4),
                         "confidence": conf, "runner_up": ({"number": new_rows[best[1][1]]["number"], "score": round(s2, 4)} if len(best) > 1 else None)})
    res = {"label": "derived", "old_instrument": old_instrument, "target": tgt, "same_law_new_edition": same_law, "rows": out_rows,
           "new_without_match": [{"number": r["number"], "provision_id": r["provision_id"]} for r in new_rows if r["provision_id"] not in used],
           "counts": {"old": len(old_rows), "new": len(new_rows), **{c: sum(1 for r in out_rows if r["confidence"] == c) for c in ("high", "medium", "low")}},
           "note": "Derived by comparing texts, not an official table. 'low' rows usually mean the rule was split, merged or dropped."}
    with _TABLE_LOCK:
        if len(_TABLE_CACHE) > 16:
            _TABLE_CACHE.clear()
        _TABLE_CACHE[key] = res
    return res


# ------------------------------------------------------------------------------------------------ article history across editions
def _same(a: str, b: str) -> bool:
    return re.sub(r"\s+", "", normalize(a)) == re.sub(r"\s+", "", normalize(b))


def article_history(pack: LawPack, ref: str | None = None, instrument: str | None = None, article: str | None = None, as_of: date | None = None,
                    lang: str = "ar") -> dict[str, Any]:
    r = resolve(pack, ref, instrument, article)
    fam = family(pack, r["instrument_id"])
    raw = []
    for iid in fam:
        pid = pack.find_provision(iid, r["number"], r["suffix"])
        if not pid:
            continue
        inst = pack.instrument(iid) or {}
        for v in pack.versions(pid):
            raw.append({"instrument_id": iid, "provision_id": pid, "edition": _edition_label(inst), "valid_from": v["valid_from"], "valid_to": v["valid_to"],
                        "trust": v["verification_status"], "pv_id": v["pv_id"], "text": _text(pack, v["pv_id"], lang),
                        "amended_by": ({"instrument_id": v["amended_by"], "number": v.get("amender_number"), "bo_number": v.get("amender_bo")} if v.get("amended_by") else None)})
    raw.sort(key=lambda x: (x["valid_from"], x["instrument_id"]))
    periods: list[dict] = []
    for x in raw:
        if periods and _same(periods[-1]["text"], x["text"]):
            p = periods[-1]  # the same words in the next edition: one period, both sources listed
            p["valid_to"] = x["valid_to"] if (not x["valid_to"] or (p["valid_to"] and x["valid_to"] > p["valid_to"])) else p["valid_to"]
            p["sources"].append({k: x[k] for k in ("instrument_id", "provision_id", "edition", "valid_from", "valid_to", "trust")})
            p["amended_by"] = p["amended_by"] or x["amended_by"]
            continue
        periods.append({**{k: x[k] for k in ("valid_from", "valid_to", "text", "amended_by", "trust")},
                        "sources": [{k: x[k] for k in ("instrument_id", "provision_id", "edition", "valid_from", "valid_to", "trust")}]})
    d = (as_of or date.today()).isoformat()
    for i, p in enumerate(periods):
        p["in_force_on_date"] = p["valid_from"] <= d and (not p["valid_to"] or p["valid_to"] > d)
        if i:
            segs = diff_texts(periods[i - 1]["text"], p["text"])
            p["diff_from_previous"] = segs
            p["change_summary"] = {"words_added": sum(len(s["text"].split()) for s in segs if s["op"] == "insert"),
                                   "words_removed": sum(len(s["text"].split()) for s in segs if s["op"] == "delete")}
        else:
            p["diff_from_previous"], p["change_summary"] = None, None
    out: dict[str, Any] = {"article": r, "family": fam, "as_of": d, "periods": periods, "changes": max(0, len(periods) - 1),
                           "in_force": next((i for i, p in enumerate(periods) if p["in_force_on_date"]), None)}
    last = periods[-1] if periods else None
    if last and last["valid_to"] and last["valid_to"] <= d:
        out["ended_on"] = last["valid_to"]
        nxt = successor_of(pack, r["instrument_id"])
        if nxt and base_id(pack, nxt) != base_id(pack, r["instrument_id"]):
            try:
                f = find_new_article(pack, instrument=r["instrument_id"], article=r["label"], target=nxt, as_of=as_of, k=3, lang=lang)
                out["continued_in"] = {"confidence": f["confidence"], "label": "derived", "target": f["target"]["instrument_id"],
                                       "matches": [{k: m[k] for k in ("provision_id", "number", "score", "text")} for m in f["matches"]]}
            except ToolError:
                pass
    out["note"] = ("Each period is a text the pack holds with its dates; a period that lists several sources had the same words in each edition. "
                   "Editions consolidated by the SGG/Adala are 'consolidated' trust: check the Bulletin officiel for a decisive point.")
    return out


def _edition_label(inst: dict) -> str:
    m = re.search(r"consolidated on (\d{4}-\d{2}-\d{2})", inst.get("status_note") or "")
    if m:
        return f"consolidated {m.group(1)}"
    return f"BO {inst['bo_number']}" if inst.get("bo_number") else (inst.get("effective_date") or "base text")


# ------------------------------------------------------------------------------------------------ articles by phrase (calculators, guides)
_LAW_CACHE: dict[tuple, list[tuple[str, str, str, str]]] = {}


def _squash(t: str) -> str:
    """Normalised and without spaces: a PDF that split a word («م بلغ») still matches the phrase."""
    return re.sub(r"\s+", "", normalize(t))


def articles_with_phrase(pack: LawPack, instrument: str, phrases: list[str], as_of: date, prefer: str | None = None, limit: int = 1) -> list[dict]:
    """Articles of a law (any of its editions, the version in force on as_of) whose text contains ALL the phrases.  `prefer`: an article
    number to try first (it is used only when it really contains the phrases: a renumbered edition is found by its words)."""
    fam = [i for i in family(pack, instrument)] if instrument in pack.instrument_ids() else [i for i in pack.instrument_ids() if i.startswith(instrument + "_")]
    if not fam:
        return []
    key = (pack.version, str(pack.path), tuple(fam), as_of.isoformat())
    if key not in _LAW_CACHE:
        if len(_LAW_CACHE) > 64:
            _LAW_CACHE.clear()
        rows = []
        for r in _law_rows(pack, fam, as_of):
            if not r["_in_force"]:
                continue
            t = _text(pack, r["pv_id"], "ar")
            rows.append((str(r["number"]), r["provision_id"], t, _squash(t), r))
        _LAW_CACHE[key] = rows
    want = [_squash(p) for p in phrases if p]
    hits = [x for x in _LAW_CACHE[key] if all(w in x[3] for w in want)]
    hits.sort(key=lambda x: (x[0] != str(prefer), _num_key(x[0])))
    return [{"provision_id": pid, "instrument_id": r["instrument_id"], "number": n, "text": t, "valid_from": r["valid_from"], "valid_to": r["valid_to"],
             "trust": r["trust"], "law": (pack.instrument(r["instrument_id"]) or {}).get("title_ar")} for n, pid, t, _s, r in hits[:limit]]


def _num_key(n: str) -> tuple:
    m = re.match(r"(\d+)", n)
    return (int(m.group(1)) if m else 10**9, n)
