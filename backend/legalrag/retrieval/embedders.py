"""Embedders. The query MUST be embedded by the same model that produced the pack's vectors
(`embedder_id`); the engine checks this and falls back to keyword search on a mismatch.

* HashingEmbedder  - dependency-free, deterministic char-n-gram hashing. Used for tests, the demo pack and as an
                     emergency local option. Lexical, NOT semantic: use BGE-M3 for real packs.
* OllamaEmbedder   - local Ollama server (e.g. `bge-m3`).
* SentenceTransformerEmbedder - local sentence-transformers model (optional dependency).
* CloudEmbedder    - OpenAI-compatible /embeddings endpoint serving the SAME model; goes through the Gateway.
"""
from __future__ import annotations

import hashlib
import re
import zlib
from typing import Callable, Protocol

import httpx
import numpy as np

from ..privacy.gateway import Gateway
from ..text.arabic import normalize, tokens


class Embedder(Protocol):
    embedder_id: str
    dim: int
    location: str  # 'local' | 'cloud'

    def embed(self, texts: list[str], case_id: str | None = None) -> np.ndarray: ...


class HashingEmbedder:
    location = "local"

    def __init__(self, embedder_id: str = "hash-ngram-v1", dim: int = 512):
        self.embedder_id, self.dim = embedder_id, dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = tokens(text)
        feats: list[tuple[str, float]] = [(f"w:{t}", 1.0) for t in toks]
        feats += [(f"b:{a}_{b}", 0.7) for a, b in zip(toks, toks[1:])]
        for t in toks:
            p = f"#{t}#"
            feats += [(f"c:{p[i:i + 3]}", 0.35) for i in range(max(1, len(p) - 2))]
        for f, w in feats:
            h = zlib.crc32(f.encode("utf-8"))
            v[h % self.dim] += (1.0 if (h >> 16) & 1 else -1.0) * w
        v = np.sign(v) * np.sqrt(np.abs(v))  # sublinear tf
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str], case_id: str | None = None) -> np.ndarray:
        return np.vstack([self._vec(t) for t in texts]) if texts else np.zeros((0, self.dim), dtype=np.float32)


class OllamaEmbedder:
    location = "local"

    def __init__(self, embedder_id: str, model: str, url: str, dim: int = 1024, client: httpx.Client | None = None):
        self.embedder_id, self.model, self.url, self.dim = embedder_id, model, url.rstrip("/"), dim
        self.client = client or httpx.Client(timeout=60)

    def embed(self, texts: list[str], case_id: str | None = None) -> np.ndarray:
        out = []
        for t in texts:
            r = self.client.post(f"{self.url}/api/embeddings", json={"model": self.model, "prompt": t})
            r.raise_for_status()
            out.append(np.asarray(r.json()["embedding"], dtype=np.float32))
        return np.vstack(out) if out else np.zeros((0, self.dim), dtype=np.float32)


class SentenceTransformerEmbedder:
    location = "local"

    def __init__(self, embedder_id: str, model: str):
        from sentence_transformers import SentenceTransformer  # optional dependency

        from ..device import pick_device

        self.embedder_id = embedder_id
        self.device = pick_device()
        self._m = SentenceTransformer(model, device=self.device)
        if self.device.startswith("cuda"):
            try:
                self._m.half()  # fp16: about twice as fast, half the memory, same quality for retrieval
            except Exception:  # noqa: BLE001
                pass
        print(f"[embedder] {embedder_id} on {self.device}", flush=True)
        self.dim = int(self._m.get_sentence_embedding_dimension())
        self._batch = 64 if self.device.startswith("cuda") else 16

    def embed(self, texts: list[str], case_id: str | None = None) -> np.ndarray:
        return np.asarray(self._m.encode(texts, normalize_embeddings=True, batch_size=self._batch, show_progress_bar=False), dtype=np.float32)


class CloudEmbedder:
    location = "cloud"

    def __init__(self, embedder_id: str, model: str, url: str, gateway: Gateway, key_getter: Callable[[], str | None], dim: int = 1024):
        self.embedder_id, self.model, self.url, self.gateway, self.key_getter, self.dim = embedder_id, model, url, gateway, key_getter, dim

    def embed(self, texts: list[str], case_id: str | None = None) -> np.ndarray:
        key = self.key_getter()
        headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
        data = self.gateway.post_json(
            kind="embed", provider="cloud-embedder", model=self.model, url=self.url, headers=headers,
            body={"model": self.model, "input": texts}, user_fields=texts, case_id=case_id,
        )
        return np.asarray([d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])], dtype=np.float32)


def stable_checksum(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()
