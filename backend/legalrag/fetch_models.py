"""Download the local models once, into <data_dir>/models (then the backend works offline).

    python -m legalrag.fetch_models                 # the reranker (BAAI/bge-reranker-v2-m3, ~2.3 GB)
    python -m legalrag.fetch_models --test          # also scores two sample pairs to prove it loads
"""
from __future__ import annotations

import argparse
import sys

from .config import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalrag.fetch_models")
    ap.add_argument("--test", action="store_true", help="load the model and score two sample pairs")
    a = ap.parse_args(argv)
    s = Settings()
    name = s.reranker_local_model
    dest = s.data_dir / "models" / name.split("/")[-1]
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("Missing package. Run:  pip install sentence-transformers", file=sys.stderr)
        return 2
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {name} -> {dest}  (first time only, a few minutes)")
    snapshot_download(repo_id=name, local_dir=str(dest), allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "tokenizer*", "sentencepiece*"],
                      ignore_patterns=["*.onnx", "onnx/*", "*.bin", "*.h5", "*.msgpack"])
    print("Downloaded.")
    if a.test:
        from .retrieval.rerankers import CrossEncoderReranker

        r = CrossEncoderReranker(str(dest), s.reranker_max_length, False, s.reranker_batch_size)
        q = "ابتداء من أي تاريخ تفقد الأوراق البنكية قوتها الإبرائية؟"
        sc = r.score(q, ["يوافق على سحب الأوراق البنكية التالية والتي تفقد قوتها الإبرائية ابتداء من فاتح يناير 2026", "تتمم أحكام الكمبيالة المسحوبة على مؤسسة بنكية"])
        print("relevant: %.3f   unrelated: %.3f" % (sc[0], sc[1]))
        return 0 if sc[0] > sc[1] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
