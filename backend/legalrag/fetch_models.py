"""Download the local models once, into <data_dir>/models (then the backend works offline).

    python -m legalrag.fetch_models                 # the reranker (BAAI/bge-reranker-v2-m3, ~2.3 GB)
    python -m legalrag.fetch_models --test          # also scores two sample pairs to prove it loads
    python -m legalrag.fetch_models --pack-embedder # also the embedding model of the INSTALLED law pack (e.g. BAAI/bge-m3, ~2.3 GB)
    python -m legalrag.fetch_models --small-reranker # ONLY the small multilingual reranker (~0.5 GB), for search by meaning through Cloudflare
"""
from __future__ import annotations

import argparse
import re
import sys

from .config import Settings


KNOWN = {"bge-m3": "BAAI/bge-m3", "bge-m3-law": "mhaseeb1604/bge-m3-law", "multilingual-e5-large": "intfloat/multilingual-e5-large"}


def fetch_pack_embedder(s: Settings, snapshot_download) -> int:
    """The installed pack names the model its vectors were made with; questions must be embedded by that same model."""
    from .store.lawpack import LawPack

    path = s.resolved_lawpack_path()
    if not path.exists():
        print(f"No law pack at {path}: install it first (tools/install_pack.py).", file=sys.stderr)
        return 1
    pack = LawPack(path)
    try:
        real = [e for e in pack.embedders().values() if not str(e["embedder_id"]).startswith("hash")]
    finally:
        pack.close()
    for e in real:
        model = str(e.get("model") or "")
        last = re.split(r"[\\/]", model.rstrip("\\/"))[-1]
        repo = model if re.fullmatch(r"[\w.-]+/[\w.-]+", model) else KNOWN.get(last)
        if not repo:
            print(f"The pack's embedding model '{model}' is not a known Hugging Face name: skipped.", file=sys.stderr)
            continue
        dest = s.resolved_embed_model_dir(model if repo == model else last)
        if (dest / "config.json").exists():
            print(f"{repo} already in {dest}")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {repo} -> {dest}  (first time only)")
        snapshot_download(repo_id=repo, local_dir=str(dest), ignore_patterns=["*.onnx", "onnx/*", "*.onnx_data", "imgs/*"])
        print("Downloaded.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalrag.fetch_models")
    ap.add_argument("--test", action="store_true", help="load the model and score two sample pairs")
    ap.add_argument("--pack-embedder", action="store_true", help="also download the embedding model named by the installed law pack")
    ap.add_argument("--small-reranker", action="store_true", help="only the small reranker (computers that search by meaning through Cloudflare)")
    a = ap.parse_args(argv)
    s = Settings()
    name = s.reranker_small_model if a.small_reranker else s.reranker_local_model
    dest = s.small_reranker_dir() if a.small_reranker else s.data_dir / "models" / name.split("/")[-1]
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Missing package. Run:  pip install sentence-transformers", file=sys.stderr)
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {name} -> {dest}  (first time only, a few minutes)")
    weights = ["*.safetensors"]
    try:   # an older repository may only have pytorch_model.bin: take it then, never both
        from huggingface_hub import HfApi

        if not any(f.endswith(".safetensors") for f in HfApi().list_repo_files(name)):
            weights = ["pytorch_model.bin"]
    except Exception:  # noqa: BLE001 - offline listing failure: try the usual files
        pass
    snapshot_download(repo_id=name, local_dir=str(dest), allow_patterns=["*.json", *weights, "*.model", "*.txt", "tokenizer*", "sentencepiece*"],
                      ignore_patterns=["*.onnx", "onnx/*", "*.h5", "*.msgpack", "*.ot"])
    print("Downloaded.")
    if a.pack_embedder and not a.small_reranker and fetch_pack_embedder(s, snapshot_download):
        return 1
    if a.test:
        from .retrieval.rerankers import CrossEncoderReranker

        r = CrossEncoderReranker(str(dest), 512 if a.small_reranker else s.reranker_max_length, False, s.reranker_batch_size)
        q = "ابتداء من أي تاريخ تفقد الأوراق البنكية قوتها الإبرائية؟"
        sc = r.score(q, ["يوافق على سحب الأوراق البنكية التالية والتي تفقد قوتها الإبرائية ابتداء من فاتح يناير 2026", "تتمم أحكام الكمبيالة المسحوبة على مؤسسة بنكية"])
        print("relevant: %.3f   unrelated: %.3f" % (sc[0], sc[1]))
        return 0 if sc[0] > sc[1] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
