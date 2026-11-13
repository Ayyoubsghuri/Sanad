"""Use the chunks and vectors that the bo_pipeline already made (chunk_bo.py -> <name>.chunks.jsonl, embed_chunks.py -> <name>.chunks.npy +
<name>.chunks.emb.json) instead of cutting and embedding the articles a second time.

Nothing is re-embedded: each pipeline chunk is stored as a `chunk` row of the pack (body = `content`, text = `embed_text`) together with
its own vector, copied as it is.  A chunk is linked to the article(s) it contains, so a hit still cites an article: a chunk that spans
several articles gets one row per article (same text, same vector); a chunk with no article (preamble, annex, table) is linked to the
first article of its text.  Provisions that no chunk covers are reported (they would be invisible to search).

Safety checks, all before anything is written:
  * the .npy has one row per chunk, in the .jsonl order, and the vectors are finite;
  * `texts_sha256` in the .emb.json matches the chunk file as it is NOW (a re-chunk after embedding is refused, not mixed);
  * every file was embedded by the same model with the same dimension."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


class PipelineImportError(Exception):
    pass


def _issue_key(s) -> str:
    return re.sub(r"[\s_\-]+", "", str(s or "")).lower()


@dataclass
class PrecomputedEmbedder:
    """Describes the vectors that come with the chunks.  Search must embed the question with the same model (same weights, normalised)."""
    embedder_id: str
    model: str
    dim: int
    location: str = "local"

    def embed(self, texts, case_id=None):  # pragma: no cover - guard
        raise PipelineImportError("these vectors were made by the pipeline; they are never recomputed here")


@dataclass
class PipelineChunks:
    records: list[dict]
    vectors: np.ndarray
    model: str
    dim: int
    files: int
    embedder: PrecomputedEmbedder = field(init=False)
    empty_files: list = field(default_factory=list)

    def __post_init__(self):
        self.embedder = PrecomputedEmbedder(self.embedder_id_default(), self.model, self.dim)

    def embedder_id_default(self) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "-", self.model.split("/")[-1]).strip("-") or "pipeline"

    def with_embedder_id(self, embedder_id: str | None) -> "PipelineChunks":
        if embedder_id:
            self.embedder.embedder_id = embedder_id
        return self

    # ---- link chunks to the pack's articles ------------------------------------------------------------------------------------------
    def plan(self, instruments: dict[str, dict], provisions: list[tuple[int, dict]]) -> tuple[list[tuple[int, int, int | None]], dict]:
        """provisions: [(pv_id, provision dict)] of the rows just written.  -> ([(pv_id, record index, paragraph_no)], report).
        paragraph_no is None for a chunk made of articles and 0 for a chunk that is not an article (preamble, annex, table): it hangs on the
        text's first article only so that it can be found, and the answer shows ITS OWN text, never that article's."""
        from .from_bo import parse_article_number

        by_issue_num: dict[tuple[str, str], list[str]] = {}
        for iid, i in instruments.items():
            if i.get("bo_number") and i.get("number"):
                by_issue_num.setdefault((_issue_key(i["bo_number"]), str(i["number"]).strip()), []).append(iid)
        pv_by: dict[tuple[str, str], int] = {}
        first_pv: dict[str, int] = {}
        for pv_id, p in provisions:
            pv_by[(p["instrument_id"], str(p["number"]).strip())] = pv_id
            first_pv.setdefault(p["instrument_id"], pv_id)

        out: list[tuple[int, int, int | None]] = []
        rep = {"chunks": len(self.records), "linked": 0, "multi_article_chunks": 0, "no_article_chunks_linked_to_first": 0,
               "unmatched_text": [], "unmatched_articles": 0, "provisions_without_chunk": 0}
        covered: set[int] = set()
        unmatched: dict[str, int] = {}
        for idx, r in enumerate(self.records):
            cands = by_issue_num.get((_issue_key(r.get("issue_number")), str(r.get("doc_number") or "").strip()), [])
            if len(cands) > 1:  # same number in the same issue under two types: use the type word in the title
                dt = (r.get("doc_type") or "").strip()
                narrowed = [c for c in cands if dt and dt.split()[0] in (instruments[c].get("title_ar") or "")]
                cands = narrowed or cands
            if not cands:
                key = f"BO {r.get('issue_number')} / {r.get('doc_type')} {r.get('doc_number')}"
                unmatched[key] = unmatched.get(key, 0) + 1
                continue
            iid = cands[0]
            pvs: list[int] = []
            for aid in r.get("article_ids") or []:
                num, _ = parse_article_number(f"المادة {aid}")
                pv = pv_by.get((iid, num)) if num else None
                if pv is None:
                    rep["unmatched_articles"] += 1
                elif pv not in pvs:
                    pvs.append(pv)
            para: int | None = None
            if not pvs:
                if iid not in first_pv:
                    continue
                pvs = [first_pv[iid]]
                para = 0
                rep["no_article_chunks_linked_to_first"] += 1
            if len(pvs) > 1:
                rep["multi_article_chunks"] += 1
            for pv in pvs:
                out.append((pv, idx, para))
                covered.add(pv)
            rep["linked"] += 1
        rep["unmatched_text"] = [{"text": k, "chunks": n} for k, n in sorted(unmatched.items(), key=lambda kv: -kv[1])[:30]]
        rep["unmatched_chunks"] = sum(unmatched.values())
        rep["provisions_without_chunk"] = sum(1 for pv_id, _p in provisions if pv_id not in covered)
        return out, rep


def load_pipeline_chunks(root: Path, only: list[Path] | None = None) -> PipelineChunks:
    """Read every <name>.chunks.jsonl (+ .npy + .emb.json) under `root` (or just `only`)."""
    root = Path(root)
    files = sorted(only) if only else sorted(p for p in root.rglob("*.chunks.jsonl") if "_frozen" not in p.parts)
    if not files:
        raise PipelineImportError(f"no *.chunks.jsonl under {root}: run chunk_bo.py and embed_chunks.py first")
    records: list[dict] = []
    mats: list[np.ndarray] = []
    model = dim = None
    empty: list[str] = []
    for f in files:
        npy, meta_f = f.with_suffix(".npy"), f.with_suffix(".emb.json")
        recs = [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]
        if not recs:  # a bulletin with nothing to chunk (cover only): embed_chunks.py writes no vectors for it either
            empty.append(f.name)
            continue
        if not npy.exists() or not meta_f.exists():
            raise PipelineImportError(f"{f.name}: no vectors yet ({npy.name} / {meta_f.name} missing): run embed_chunks.py")
        meta = json.loads(meta_f.read_text("utf-8"))
        vec = np.load(npy)
        if vec.ndim != 2 or vec.shape[0] != len(recs):
            raise PipelineImportError(f"{f.name}: {len(recs)} chunks but {vec.shape[0] if vec.ndim == 2 else '?'} vectors")
        if not np.isfinite(vec).all():
            raise PipelineImportError(f"{npy.name}: contains NaN/inf")
        field_name = meta.get("field", "embed_text")
        texts = [meta.get("prefix_doc", "") + r[field_name] for r in recs]
        sha = hashlib.sha256("\n".join(f"{r['chunk_id']}\0{t}" for r, t in zip(recs, texts)).encode("utf-8")).hexdigest()
        if meta.get("texts_sha256") and meta["texts_sha256"] != sha:
            raise PipelineImportError(f"{f.name} was changed after it was embedded: run embed_chunks.py again (or chunk_bo.py --overwrite then embed)")
        if model is None:
            model, dim = meta["model"], int(meta["dim"])
        elif meta["model"] != model or int(meta["dim"]) != dim:
            raise PipelineImportError(f"{f.name}: embedded with {meta['model']} ({meta['dim']}), the other files with {model} ({dim}): vectors cannot be mixed")
        records += recs
        mats.append(vec.astype(np.float32, copy=False))
    if not mats:
        raise PipelineImportError(f"all {len(files)} chunk files are empty")
    out = PipelineChunks(records, np.vstack(mats), model, dim, len(files) - len(empty))
    out.empty_files = empty
    return out
