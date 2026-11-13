#!/usr/bin/env python3
"""
embed_chunks.py  --  embed the chunks written by chunk_bo.py.

  1. downloads the embedding model from Hugging Face the first time (into --model-dir, default ./models/<name>)
     and reuses that local copy afterwards (works offline once downloaded),
  2. embeds the `embed_text` of every chunk in every <name>.chunks.jsonl found under PATH,
  3. saves  <name>.chunks.npy  (float32, L2-normalised, same row order as the .jsonl)
            <name>.chunks.emb.json (model, dim, text field, how many chunks were cut by the 512-token limit),
  4. optional: --index-dir DIR  also writes one combined index (embeddings.npy + chunks.jsonl) for a vector store,
  5. --search "question"  /  --eval queries.jsonl  to test retrieval quality on YOUR data before you trust a model.

Default model: BAAI/bge-m3  (1024 dim, up to 8192 tokens, strong on Arabic, no prefixes needed).  Others (short names work):
  --model bge-m3-law     mhaseeb1604/bge-m3-law   (bge-m3 fine-tuned on Arabic/English law; no published benchmark)
  --model e5 --prefix-doc "passage: " --prefix-query "query: "     intfloat/multilingual-e5-large
  --model dz-legal       Monad-dz/dz-legal-ar-embeddings-v1  (Algerian court decisions, 512 tokens; chunk with --profile bert512)
Any sentence-transformers model id works.

Install:  pip install -U sentence-transformers huggingface_hub numpy
Examples:
  python embed_chunks.py /data/bo                                   # download model + embed everything
  python embed_chunks.py /data/bo --index-dir /data/bo_index
  python embed_chunks.py /data/bo --search "رخصة المرض المتوسطة للقضاة" --top 5
  python embed_chunks.py /data/bo --eval my_queries.jsonl           # {"query": "...", "relevant": ["BO7373-003-00", ...]}
  python embed_chunks.py /data/bo --model bge-m3-law --index-dir /data/idx_law --eval my_queries.jsonl   # compare models
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

import numpy as np

DEFAULT_MODEL = "BAAI/bge-m3"
ALIASES = {                                   # short names for --model
    "bge-m3": "BAAI/bge-m3",
    "bge-m3-law": "mhaseeb1604/bge-m3-law",
    "e5": "intfloat/multilingual-e5-large",
    "dz-legal": "Monad-dz/dz-legal-ar-embeddings-v1",
}


# ----------------------------------------------------------------------------- model loading
class HashModel:
    """Offline stand-in for plumbing tests only (character n-gram hashing, NOT semantic).  --model hash:256"""
    max_seq_length = 512
    tokenizer = None

    def __init__(self, dim):
        self.dim = dim

    def encode(self, texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True, **kw):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            t = re.sub(r"\s+", " ", t)
            for n in (3, 4):
                for j in range(len(t) - n + 1):
                    h = int(hashlib.md5(t[j:j + n].encode()).hexdigest()[:8], 16)
                    out[i, h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        if normalize_embeddings:
            out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)
        return out


def load_model(name: str, model_dir: str | None, device: str | None, offline: bool, max_seq: int = 1024):
    name = ALIASES.get(name, name)
    if name.startswith("hash:"):
        return HashModel(int(name.split(":")[1] or 256)), name
    from sentence_transformers import SentenceTransformer
    local = Path(model_dir or Path("models") / name.split("/")[-1])
    if not (local / "config.json").exists():
        if offline:
            sys.exit(f"model not found in {local} and --offline was given")
        from huggingface_hub import snapshot_download
        print(f"downloading {name} -> {local} (first run only)", file=sys.stderr)
        local.mkdir(parents=True, exist_ok=True)
        snapshot_download(repo_id=name, local_dir=str(local))
    else:
        print(f"using local model copy {local}", file=sys.stderr)
    m = SentenceTransformer(str(local), device=device)
    m.max_seq_length = min(int(m.max_seq_length or 512), max_seq)         # bge-m3 allows 8192; our chunks never need that
    return m, str(local)


def n_tokens(model, texts):
    tk = getattr(model, "tokenizer", None)
    if tk is None:
        return [len(t.split()) * 2 for t in texts]
    return [len(x) for x in tk(texts, add_special_tokens=True, truncation=False)["input_ids"]]


# ----------------------------------------------------------------------------- io
def find_chunk_files(path: Path):
    return [path] if path.is_file() else sorted(path.rglob("*.chunks.jsonl"))


def read_chunks(f: Path):
    return [json.loads(l) for l in f.open(encoding="utf-8") if l.strip()]


def npy_of(f: Path):
    return f.with_suffix(".npy")


def meta_of(f: Path):
    return f.with_suffix(".emb.json")


def embed_file(model, f: Path, a):
    chunks = read_chunks(f)
    if not chunks:
        return None
    npy, meta = npy_of(f), meta_of(f)
    texts = [a.prefix_doc + c[a.field] for c in chunks]
    # fingerprint of the exact texts + ids: a re-chunk that keeps the same NUMBER of chunks must still re-embed
    texts_sha = hashlib.sha256("\n".join(f"{c['chunk_id']}\0{t}" for c, t in zip(chunks, texts)).encode("utf-8")).hexdigest()
    if npy.exists() and meta.exists() and not a.overwrite:
        m = json.loads(meta.read_text())
        if (m.get("model") == a.model and m.get("count") == len(chunks) and m.get("field") == a.field
                and m.get("texts_sha256") == texts_sha and np.load(npy, mmap_mode="r").shape[0] == len(chunks)):
            print(f"skip (up to date): {f}", file=sys.stderr)
            return None
        print(f"re-embedding (chunks, model or settings changed since the last run): {f}", file=sys.stderr)
    limit = int(getattr(model, "max_seq_length", 512) or 512)
    lens = n_tokens(model, texts)
    over = [i for i, n in enumerate(lens) if n > limit]
    emb = model.encode(texts, batch_size=a.batch, show_progress_bar=True, normalize_embeddings=True)
    emb = np.asarray(emb, dtype=np.float32)
    np.save(npy, emb)
    meta.write_text(json.dumps({"model": a.model, "dim": int(emb.shape[1]), "count": len(chunks), "field": a.field,
                                "normalized": True, "max_seq_length": limit, "truncated_chunks": len(over),
                                "truncated_ids": [chunks[i]["chunk_id"] for i in over][:50],
                                "max_tokens": int(max(lens)), "prefix_doc": a.prefix_doc,
                                "texts_sha256": texts_sha, "source_sha256": chunks[0].get("source_sha256")}, ensure_ascii=False, indent=1))
    pct = 100 * len(over) / len(chunks)
    flag = "" if not over else f"  !! {len(over)} chunks ({pct:.1f}%) exceed {limit} tokens and were CUT -> raise --max-seq (if the model allows) or re-chunk with --profile bert512"
    print(f"{f.name}: {len(chunks)} chunks, dim {emb.shape[1]}, longest {max(lens)} tokens{flag}", file=sys.stderr)
    return chunks, emb


def load_index(path: Path):
    """all chunks + embeddings under PATH (or an --index-dir)"""
    if path.is_dir() and (path / "embeddings.npy").exists():
        return read_chunks(path / "chunks.jsonl"), np.load(path / "embeddings.npy")
    chunks, embs = [], []
    for f in find_chunk_files(path):
        if not npy_of(f).exists():
            continue
        c = read_chunks(f)
        e = np.load(npy_of(f))
        if len(c) == len(e):
            chunks += c; embs.append(e)
    if not chunks:
        sys.exit("no embeddings found - run the embedding step first")
    return chunks, np.vstack(embs)


# ----------------------------------------------------------------------------- search / eval
def search(model, chunks, emb, query, a, top=5):
    q = np.asarray(model.encode([a.prefix_query + query], normalize_embeddings=True), dtype=np.float32)[0]
    sc = emb @ q
    idx = np.argsort(-sc)[:top]
    return [(float(sc[i]), chunks[i]) for i in idx]


def evaluate(model, chunks, emb, qfile: Path, a):
    qs = [json.loads(l) for l in qfile.open(encoding="utf-8") if l.strip()]
    ids = [c["chunk_id"] for c in chunks]
    docs = [c["doc_id"] for c in chunks]
    Q = np.asarray(model.encode([a.prefix_query + q["query"] for q in qs], batch_size=a.batch, normalize_embeddings=True), dtype=np.float32)
    S = Q @ emb.T
    ks = (1, 3, 5, 10)
    hit = {k: 0 for k in ks}; rr = 0.0
    for qi, q in enumerate(qs):
        rel = set(q.get("relevant", [])); rel_docs = set(q.get("relevant_docs", []))
        order = np.argsort(-S[qi])
        rank = None
        for r, j in enumerate(order[:100], 1):
            if ids[j] in rel or docs[j] in rel_docs:
                rank = r; break
        if rank:
            rr += 1 / rank
            for k in ks:
                hit[k] += rank <= k
    n = len(qs)
    res = {f"recall@{k}": round(hit[k] / n, 4) for k in ks}; res["MRR"] = round(rr / n, 4); res["queries"] = n
    return res


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Embed BO chunks (downloads the model on first use)")
    ap.add_argument("path", help="folder (all sub-folders) or one .chunks.jsonl made by chunk_bo.py")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Hugging Face model id (or hash:256 for an offline plumbing test)")
    ap.add_argument("--max-seq", type=int, default=1024, help="cap on tokens per chunk fed to the model (memory/speed)")
    ap.add_argument("--model-dir", help="where the model is stored (default ./models/<model name>)")
    ap.add_argument("--offline", action="store_true", help="never download; fail if the model is not in --model-dir")
    ap.add_argument("--field", default="embed_text", choices=["embed_text", "content"], help="text to embed (default: header + content)")
    ap.add_argument("--prefix-doc", default="", help='e.g. "passage: " for e5 models')
    ap.add_argument("--prefix-query", default="", help='e.g. "query: " for e5 models')
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--device", help="cpu / cuda / mps (default: automatic)")
    ap.add_argument("--index-dir", help="also write a combined index here (embeddings.npy, chunks.jsonl, index.json)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--search", help="print the best chunks for this question and exit")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--eval", help='queries .jsonl: {"query": "...", "relevant": [chunk ids]} and/or {"relevant_docs": [doc ids]}')
    a = ap.parse_args()

    a.model = ALIASES.get(a.model, a.model)
    model, local = load_model(a.model, a.model_dir, a.device, a.offline, a.max_seq)
    src = Path(a.path)

    if a.search or a.eval:
        chunks, emb = load_index(Path(a.index_dir) if a.index_dir else src)
        if a.search:
            for s, c in search(model, chunks, emb, a.search, a, a.top):
                print(f"{s:.3f}  {c['chunk_id']}  ص{c['pages'][0]}  {c['title'][:90]}\n        {c['content'][:200].replace(chr(10), ' ')}\n")
        if a.eval:
            print(json.dumps(evaluate(model, chunks, emb, Path(a.eval), a), ensure_ascii=False, indent=1))
        return

    files = find_chunk_files(src)
    if not files:
        sys.exit("no *.chunks.jsonl found - run chunk_bo.py first")
    for f in files:
        embed_file(model, f, a)
    if a.index_dir:
        chunks, emb = load_index(src)
        out = Path(a.index_dir); out.mkdir(parents=True, exist_ok=True)
        np.save(out / "embeddings.npy", emb)
        with (out / "chunks.jsonl").open("w", encoding="utf-8") as fh:
            for c in chunks:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        (out / "index.json").write_text(json.dumps({"model": a.model, "dim": int(emb.shape[1]), "count": len(chunks),
                                                    "field": a.field, "normalized": True, "prefix_query": a.prefix_query}, indent=1))
        print(f"index: {len(chunks)} chunks -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
