"""Pipeline chunks + vectors are stored as they are (no re-embedding) in a new pack and in an appended one."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from legalrag.builder.append import AppendError, append_sources
from legalrag.builder.build import build_pack
from legalrag.builder.from_bo import bo_to_sources
from legalrag.builder.pipeline_import import PipelineImportError, load_pipeline_chunks
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.store.lawpack import LawPack

from test_bo_update import _md


def _write_pipeline(folder: Path, name: str, src: dict, model="BAAI/bge-m3", dim=8, seed=1, tamper=False) -> np.ndarray:
    """What chunk_bo.py + embed_chunks.py leave next to <name>.md (same field names, same texts_sha256 rule)."""
    folder.mkdir(parents=True, exist_ok=True)
    recs = []
    for i in src["instruments"]:
        provs = [p for p in src["provisions"] if p["instrument_id"] == i["instrument_id"]]
        base = {"issue_number": i["bo_number"], "doc_type": "قرار", "doc_number": i["number"]}
        recs.append({**base, "chunk_id": f"BO{i['bo_number']}-{len(recs):03d}", "chunk_type": "preamble", "article_ids": [], "content": "ديباجة " + i["title_ar"], "embed_text": f"ديباجة {i['bo_number']}\n\n" + i["title_ar"]})
        for p in provs:
            body = p["versions"][0]["texts"]["ar"]["text"]
            recs.append({**base, "chunk_id": f"BO{i['bo_number']}-{len(recs):03d}", "chunk_type": "article", "article_ids": [p["number"].replace(" bis", " مكرر")],
                         "content": body, "embed_text": f"رأس {i['bo_number']}-{len(recs)}\n\n" + body})
        if len(provs) > 1:  # one chunk that holds two articles
            recs.append({**base, "chunk_id": f"BO{i['bo_number']}-{len(recs):03d}", "chunk_type": "article",
                         "article_ids": [provs[0]["number"], provs[1]["number"]], "content": "مادتان", "embed_text": f"رأس {i['bo_number']}-{len(recs)}\n\nمادتان"})
    rng = np.random.default_rng(seed)
    vec = rng.normal(size=(len(recs), dim)).astype(np.float32)
    vec /= np.linalg.norm(vec, axis=1, keepdims=True)
    sha = hashlib.sha256("\n".join(f"{r['chunk_id']}\0{r['embed_text']}" for r in recs).encode()).hexdigest()
    (folder / f"{name}.chunks.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), "utf-8")
    np.save(folder / f"{name}.chunks.npy", vec)
    (folder / f"{name}.chunks.emb.json").write_text(json.dumps({"model": model, "dim": dim, "count": len(recs), "field": "embed_text", "prefix_doc": "",
                                                              "texts_sha256": "bad" if tamper else sha}))
    return vec


class Boom(HashingEmbedder):
    def embed(self, texts, case_id=None):
        raise AssertionError("nothing may be embedded again")


def test_build_pack_stores_the_pipeline_vectors_unchanged(tmp_path):
    src, _ = bo_to_sources([_md(tmp_path)])
    vec = _write_pipeline(tmp_path / "pc", "BO_7499_Ar", src)
    pipe = load_pipeline_chunks(tmp_path / "pc").with_embedder_id("bge-m3")
    res = build_pack(src, tmp_path / "p.db", [Boom()], "pv-1", pipeline=pipe)
    assert res.stats["built"], res.report.to_dict()
    assert res.stats["pipeline"]["unmatched_chunks"] == 0
    db = sqlite3.connect(tmp_path / "p.db")
    assert db.execute("SELECT embedder_id,model,dim FROM embedder").fetchall() == [("bge-m3", "BAAI/bge-m3", 8)]
    assert db.execute("SELECT value FROM pack_meta WHERE key='chunk_source'").fetchone()[0] == "pipeline"
    got = {r[0]: np.frombuffer(r[1], dtype=np.float32) for r in db.execute("SELECT c.text,e.vector FROM chunk c JOIN chunk_embedding e USING(chunk_id)")}
    for r, v in zip(pipe.records, vec):  # byte-for-byte the pipeline's row
        assert np.array_equal(got[r["embed_text"]], v)
    # the two-article chunk is reachable from both articles; the preamble hangs on the first article
    n_two = db.execute("SELECT COUNT(*) FROM chunk WHERE body='مادتان'").fetchone()[0]
    assert n_two == 2 * sum(1 for r in pipe.records if r['content'] == 'مادتان') > 0
    assert res.stats["pipeline"]["no_article_chunks_linked_to_first"] >= 1
    n_other = db.execute("SELECT COUNT(*) FROM chunk WHERE paragraph_no=0").fetchone()[0]
    assert n_other == res.stats["pipeline"]["no_article_chunks_linked_to_first"]  # preamble chunks are marked: shown with their own text
    assert db.execute("SELECT COUNT(*) FROM chunk WHERE paragraph_no IS NULL").fetchone()[0] > 0
    db.close()
    p = LawPack(tmp_path / "p.db")
    assert p.vector_index("bge-m3") is not None
    p.close()


def test_append_with_pipeline_chunks(tmp_path, pack_path):
    # a pack that was itself made from pipeline chunks
    s1, _ = bo_to_sources([_md(tmp_path / "a" if (tmp_path / "a").mkdir() is None else tmp_path, "7499")])
    _write_pipeline(tmp_path / "pc1", "BO_7499_Ar", s1, seed=1)
    pipe1 = load_pipeline_chunks(tmp_path / "pc1").with_embedder_id("bge-m3")
    assert build_pack(s1, tmp_path / "base.db", [Boom()], "v1", pipeline=pipe1).stats["built"]
    before = sqlite3.connect(tmp_path / "base.db").execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    # a new issue with its own chunks/vectors
    (tmp_path / "b").mkdir()
    s2, _ = bo_to_sources([_md(tmp_path / "b", "7500")])
    v2 = _write_pipeline(tmp_path / "pc2", "BO_7500_Ar", s2, seed=2)
    pipe2 = load_pipeline_chunks(tmp_path / "pc2").with_embedder_id("bge-m3")
    work = tmp_path / "w.db"
    shutil.copy2(tmp_path / "base.db", work)
    res = append_sources(work, s2, Boom(), "v2", pipeline=pipe2)
    assert res["chunks"] == len(pipe2.records) + res["pipeline"]["multi_article_chunks"]
    db = sqlite3.connect(work)
    assert db.execute("SELECT COUNT(*) FROM chunk").fetchone()[0] == before + res["chunks"]
    assert db.execute("SELECT COUNT(*) FROM chunk_embedding").fetchone()[0] == before + res["chunks"]
    row = db.execute("SELECT e.vector FROM chunk c JOIN chunk_embedding e USING(chunk_id) WHERE c.text=?", (pipe2.records[1]["embed_text"],)).fetchone()
    assert np.array_equal(np.frombuffer(row[0], dtype=np.float32), v2[1])
    db.close()


def test_append_refuses_vectors_from_another_model(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    s1, _ = bo_to_sources([_md(tmp_path / "a", "7499")])
    _write_pipeline(tmp_path / "pc1", "BO_7499_Ar", s1)
    assert build_pack(s1, tmp_path / "base.db", [Boom()], "v1", pipeline=load_pipeline_chunks(tmp_path / "pc1").with_embedder_id("bge-m3")).stats["built"]
    s2, _ = bo_to_sources([_md(tmp_path / "b", "7500")])
    _write_pipeline(tmp_path / "pc2", "BO_7500_Ar", s2, model="intfloat/multilingual-e5-large")
    with pytest.raises(AppendError, match="embedded with|same model"):
        append_sources(tmp_path / "base.db", s2, Boom(), "v2", pipeline=load_pipeline_chunks(tmp_path / "pc2").with_embedder_id("bge-m3"))


def test_stale_or_mismatched_pipeline_files_are_refused(tmp_path):
    s, _ = bo_to_sources([_md(tmp_path)])
    _write_pipeline(tmp_path / "t", "BO_7499_Ar", s, tamper=True)
    with pytest.raises(PipelineImportError, match="changed after it was embedded"):
        load_pipeline_chunks(tmp_path / "t")
    _write_pipeline(tmp_path / "m", "BO_7499_Ar", s)
    np.save(tmp_path / "m" / "BO_7499_Ar.chunks.npy", np.zeros((2, 8), dtype=np.float32))
    with pytest.raises(PipelineImportError, match="vectors"):
        load_pipeline_chunks(tmp_path / "m")
    _write_pipeline(tmp_path / "x", "BO_7499_Ar", s)
    _write_pipeline(tmp_path / "x", "BO_7500_Ar", s, model="other")
    with pytest.raises(PipelineImportError, match="cannot be mixed"):
        load_pipeline_chunks(tmp_path / "x")
    with pytest.raises(PipelineImportError, match="no \\*.chunks.jsonl"):
        load_pipeline_chunks(tmp_path / "empty")


def test_no_settings_needed_key_pipeline_and_embedder(tmp_path):
    """The machine's own signing key, the bundled scripts and the pack's own embedder replace three env settings."""
    from legalrag.builder.cli import main as build_main
    from legalrag.config import Settings
    from legalrag.state import build_context
    from legalrag.store.localkey import effective_public_key, local_private_key, public_from_private
    from legalrag.bo_update.runner import BoUpdater
    import json as _json

    data = tmp_path / "data"
    s = Settings(data_dir=data, lawpack_path=data / "lawpack" / "current.db", default_mode="hybrid")
    assert effective_public_key(s) is None and local_private_key(s) is None
    (tmp_path / "a").mkdir()
    src, _ = bo_to_sources([_md(tmp_path / "a")])
    _write_pipeline(tmp_path / "pc", "BO_7499_Ar", src)
    (tmp_path / "s.json").write_text(_json.dumps(src, ensure_ascii=False), "utf-8")
    import os
    os.environ["LEGALRAG_DATA_DIR"] = str(data)
    try:
        rc = build_main(["build", str(tmp_path / "s.json"), "--out", str(data / "lawpack" / "current.db"), "--version", "k1",
                         "--pipeline-chunks", str(tmp_path / "pc"), "--embedder-id", "bge-m3"])
    finally:
        os.environ.pop("LEGALRAG_DATA_DIR")
    assert rc == 0
    priv = local_private_key(s)
    assert priv and effective_public_key(s) == public_from_private(priv)
    ctx = build_context(s)
    assert ctx.pack_usable() and ctx.pack_trust.state == "signed_valid"  # trusted with no public key configured
    # the pack's embedder is picked without LEGALRAG_EMBEDDER_* (the model itself is not loaded here)
    assert s.resolved_bo_pipeline_dir().joinpath("extract_bo_pdf.py").exists()
    assert s.resolved_bo_pipeline_dir().joinpath("chunk_bo.py").exists() and s.resolved_bo_pipeline_dir().joinpath("embed_chunks.py").exists()
    assert (s.resolved_bo_pipeline_dir() / "glyph_fixes.json").exists()
    ctx.embedder_override = HashingEmbedder("bge-m3", 8)  # sentence-transformers is not installed in the test environment
    probs = BoUpdater(ctx).problems()
    assert not any("key" in p.lower() for p in probs), probs
    assert not any("pipeline" in p.lower() and "not found" in p.lower() for p in probs), probs


def test_article_pages_and_page_image_route(tmp_path):
    """The pack knows where each article sits in the official PDF; the page image route serves only that article's pages."""
    import shutil as _sh
    from fastapi.testclient import TestClient
    from pypdf import PdfWriter

    from conftest import H
    from legalrag.builder.from_bo import freeze_pdfs
    from legalrag.config import Settings
    from legalrag.main import create_app
    from legalrag.state import build_context

    md_dir, pdf_dir, fr = tmp_path / "md", tmp_path / "pdf", tmp_path / "fr"
    md_dir.mkdir(); pdf_dir.mkdir()
    md = _md(md_dir, "7499")
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=300, height=400)
    with (pdf_dir / "BO_7499_Ar.pdf").open("wb") as f:
        w.write(f)
    freeze_pdfs(pdf_dir, fr)
    src, _ = bo_to_sources([md], pdf_dir, fr, md_dir)
    assert all(p.get("page") for p in src["provisions"])
    assert any(s.get("url", "").startswith("file:") for s in src["sources"])
    data = tmp_path / "data"
    assert build_pack(src, data / "lawpack" / "current.db", [HashingEmbedder()], "t1").stats["built"]
    s = Settings(data_dir=data, lawpack_path=data / "lawpack" / "current.db", allow_unsigned_pack=True)
    ctx = build_context(s)
    from conftest import TOKEN
    ctx.api_token = TOKEN
    c = TestClient(create_app(s, ctx))
    pid = src["provisions"][0]["provision_id"] if src["provisions"][0].get("provision_id") else None
    pid = pid or ctx.pack._one("SELECT provision_id FROM provision LIMIT 1")["provision_id"]
    ev = c.get(f"/v1/provisions/{pid}/evidence?as_of=2030-01-01", headers=H)
    assert ev.status_code == 200, ev.text
    j = ev.json()
    assert j["pdf_available"] and j["total_pages"] == 3 and j["page_start"] >= 1
    img = c.get(f"/v1/provisions/{pid}/page/{j['page_start']}?as_of=2030-01-01", headers=H)
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert c.get(f"/v1/provisions/{pid}/page/{j['page_end'] + 1}?as_of=2030-01-01", headers=H).status_code == 403  # not this article's page
    assert c.get(f"/v1/provisions/{pid}/page/1?as_of=2030-01-01").status_code == 401


def test_empty_chunk_file_is_skipped_not_fatal(tmp_path):
    s, _ = bo_to_sources([_md(tmp_path)])
    _write_pipeline(tmp_path / "e", "BO_7499_Ar", s)
    (tmp_path / "e" / "BO_7009_Ar.chunks.jsonl").write_text("", "utf-8")  # no .npy / .emb.json: embed_chunks.py writes none for an empty file
    pc = load_pipeline_chunks(tmp_path / "e")
    assert pc.empty_files == ["BO_7009_Ar.chunks.jsonl"] and len(pc.records) == len(pc.vectors)
    # a non-empty file without vectors is still refused
    (tmp_path / "e" / "BO_7010_Ar.chunks.jsonl").write_text(json.dumps({"chunk_id": "x", "embed_text": "t", "content": "t"}) + "\n", "utf-8")
    with pytest.raises(PipelineImportError, match="no vectors yet"):
        load_pipeline_chunks(tmp_path / "e")


def test_non_article_chunk_is_shown_with_its_own_text(tmp_path):
    from datetime import date
    from types import SimpleNamespace

    from legalrag.verify import renderer

    src, _ = bo_to_sources([_md(tmp_path)])
    _write_pipeline(tmp_path / "pc", "BO_7499_Ar", src)
    pipe = load_pipeline_chunks(tmp_path / "pc").with_embedder_id("bge-m3")
    assert build_pack(src, tmp_path / "p.db", [Boom()], "v", pipeline=pipe).stats["built"]
    pack = LawPack(tmp_path / "p.db")
    other = pack._one("SELECT chunk_id FROM chunk WHERE paragraph_no=0 LIMIT 1")["chunk_id"]
    art = pack._one("SELECT chunk_id FROM chunk WHERE paragraph_no IS NULL AND body NOT LIKE 'مادتان' LIMIT 1")["chunk_id"]
    for cid, kind in ((other, "other_text"), (art, "article")):
        ch = pack.chunks([cid])[cid]
        e = renderer.source_entry(pack, SimpleNamespace(chunk=ch, source="vector", note="", via="", score=0.5), "fr", date(2030, 1, 1), f"C{cid}")
        assert e["kind"] == kind
        if kind == "other_text":
            assert e["text"] == ch.body and e["pages"] is None and not e["has_pdf"] and "annexe" in e["article"]
        else:
            assert e["article"].lower().startswith("article") or e["article"]  # the whole article, labelled with its number
    pack.close()
