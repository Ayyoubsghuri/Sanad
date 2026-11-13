"""legalrag-build: genkey | build | verify | fixture | watch"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..retrieval.embedders import HashingEmbedder, OllamaEmbedder, SentenceTransformerEmbedder
from ..store import signing
from .build import build_pack
from .fixtures import fixture_sources
from .loader import load_sources
from .watch import watch


def _embedders(kinds: list[str], model: str, url: str):
    out = []
    for k in kinds:
        if k == "hash":
            out.append(HashingEmbedder())
        elif k == "ollama":
            out.append(OllamaEmbedder("bge-m3", model, url))
        elif k == "st":
            out.append(SentenceTransformerEmbedder("bge-m3", "BAAI/bge-m3"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalrag-build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("genkey", help="generate an Ed25519 signing keypair")
    b = sub.add_parser("build", help="build + sign a law pack from a sources directory")
    b.add_argument("sources", type=Path)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--version", required=True)
    b.add_argument("--private-key-hex")
    b.add_argument("--embedder", action="append", default=["hash"], choices=["hash", "ollama", "st"])
    b.add_argument("--ollama-model", default="bge-m3")
    b.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    b.add_argument("--allow-errors", action="store_true")
    b.add_argument("--pipeline-chunks", type=Path, help="folder with the .chunks.jsonl/.npy/.emb.json made by chunk_bo.py + embed_chunks.py: they are used as they are, NOTHING is re-embedded")
    b.add_argument("--embedder-id", default=None, help="id stored in the pack for those vectors (default: model name, e.g. bge-m3); LEGALRAG_EMBEDDER_ID must equal it")
    f = sub.add_parser("fixture", help="build the SYNTHETIC fixture pack (not real law)")
    f.add_argument("--out", type=Path, required=True)
    f.add_argument("--private-key-hex")
    v = sub.add_parser("verify", help="verify a pack signature")
    v.add_argument("pack", type=Path)
    v.add_argument("--public-key-hex", required=True)
    o = sub.add_parser("from-bo", help="turn extracted BO markdown (extract_bo_pdf.py output) into builder sources: freeze PDFs, split into dated provisions, link, check")
    o.add_argument("md_dir", type=Path, help="folder with the BO .md files (sub-folders included)")
    o.add_argument("--pdf-dir", type=Path, help="folder with the original PDFs: copied unchanged + hashed into --frozen-dir")
    o.add_argument("--frozen-dir", type=Path, help="read-only copy of the PDFs + manifest.json (default: <md_dir>/_frozen when --pdf-dir is given)")
    o.add_argument("--out", type=Path, required=True, help="sources .json to write (feed it to: legalrag-build build)")
    o.add_argument("--report", type=Path, help="write the full ingest report here (json)")
    w = sub.add_parser("watch", help="hash-check official source URLs for changes")
    w.add_argument("--urls", type=Path, required=True, help="JSON list of {name,url}")
    w.add_argument("--state", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "from-bo":
        from . import checks
        from .from_bo import bo_to_sources, freeze_pdfs

        frozen = a.frozen_dir or (a.md_dir / "_frozen" if a.pdf_dir else None)
        freeze = freeze_pdfs(a.pdf_dir, frozen) if a.pdf_dir else None
        mds = sorted(p for p in a.md_dir.rglob("*.md") if "_frozen" not in p.parts)
        src, rep = bo_to_sources(mds, a.pdf_dir, frozen, a.md_dir)
        check = checks.Report()
        checks.check_sources(src, check)
        out = {"freeze": freeze, "ingest": rep, "checks": check.to_dict()}
        a.out.write_text(json.dumps(src, ensure_ascii=False, indent=1), "utf-8")
        if a.report:
            a.report.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
        print(json.dumps({"freeze": freeze, "instruments": rep["instruments"], "articles": rep["articles"], "skipped": len(rep["skipped"]),
                          "warnings": len(rep["warnings"]), "check_errors": len(check.errors), "check_warnings": len(check.warnings)}, ensure_ascii=False, indent=1))
        return 0 if not check.errors else 2
    if a.cmd == "genkey":
        priv, pub = signing.generate_keypair()
        print(json.dumps({"private_key_hex": priv, "public_key_hex": pub}, indent=2))
        print("Keep the private key on the build machine; ship the public key with the app (LEGALRAG_LAWPACK_PUBLIC_KEY_HEX).", file=sys.stderr)
        return 0
    if a.cmd in ("build", "fixture"):
        pipe = None
        if a.cmd == "build" and a.pipeline_chunks:
            from .pipeline_import import PipelineImportError, load_pipeline_chunks

            try:
                pipe = load_pipeline_chunks(a.pipeline_chunks).with_embedder_id(a.embedder_id)
            except PipelineImportError as e:
                print(f"pipeline chunks refused: {e}", file=sys.stderr)
                return 2
            print(f"using {len(pipe.records)} pipeline chunks from {pipe.files} files ({pipe.model}, dim {pipe.dim}) - no re-embedding", file=sys.stderr)
            if pipe.empty_files:
                print(f"{len(pipe.empty_files)} chunk file(s) are empty (nothing to embed): {', '.join(pipe.empty_files[:10])}", file=sys.stderr)
        if a.cmd == "build":
            src, embs, ver = load_sources(a.sources), ([] if pipe else _embedders(list(dict.fromkeys(a.embedder)), a.ollama_model, a.ollama_url)), a.version
        else:
            src, embs, ver = fixture_sources(), _embedders(["hash"], "", ""), "fixture-0"
        priv = getattr(a, "private_key_hex", None)
        if a.cmd == "build" and not priv:  # no key given: this machine's own key, made on first use (the app trusts it automatically)
            from ..config import Settings
            from ..store.localkey import local_private_key, public_from_private

            priv = local_private_key(Settings(), create=True)
            print(f"signing with this machine's key (public key {public_from_private(priv)[:16]}...): the app trusts it automatically", file=sys.stderr)
        res = build_pack(src, a.out, embs, ver, priv, allow_errors=getattr(a, "allow_errors", False), pipeline=pipe)
        print(json.dumps({"stats": res.stats, "report": res.report.to_dict()}, ensure_ascii=False, indent=2))
        return 0 if res.stats.get("built") else 1
    if a.cmd == "verify":
        t = signing.verify_pack(a.pack, a.public_key_hex)
        print(t.state, t.detail)
        return 0 if t.ok else 1
    if a.cmd == "watch":
        changes = watch(json.loads(a.urls.read_text()), a.state)
        print(json.dumps(changes, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
