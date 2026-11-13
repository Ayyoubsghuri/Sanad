"""Article-level chunking: one chunk per article; split above ~800 tokens by paragraph. Every chunk is
prefixed (for embedding / keyword indexing) with law title, hierarchy path, article number and validity dates."""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_TOKENS = 800


def approx_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.4))


@dataclass
class ChunkSpec:
    paragraph_no: int | None
    body: str
    text: str  # context-prefixed


def context_prefix(lang: str, title: str, path: str | None, number: str, valid_from: str, valid_to: str | None) -> str:
    label = "المادة" if lang == "ar" else "Article"
    return f"{title}\n{path or ''}\n{label} {number} · {valid_from} → {valid_to or '...'}\n"


def split_paragraphs(body: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n|\n(?=\s*(?:\d+[\.\-°)]|[-–•]))", body) if p.strip()]
    return parts or [body.strip()]


def make_chunks(body: str, prefix: str, max_tokens: int = MAX_TOKENS) -> list[ChunkSpec]:
    body = body.strip()
    if approx_tokens(body) <= max_tokens:
        return [ChunkSpec(None, body, prefix + body)]
    chunks: list[ChunkSpec] = []
    buf: list[str] = []
    first_no = 1
    n = 0
    for i, para in enumerate(split_paragraphs(body), start=1):
        t = approx_tokens(para)
        if buf and n + t > max_tokens:
            b = "\n\n".join(buf)
            chunks.append(ChunkSpec(first_no, b, prefix + b))
            buf, n, first_no = [], 0, i
        buf.append(para)
        n += t
    if buf:
        b = "\n\n".join(buf)
        chunks.append(ChunkSpec(first_no, b, prefix + b))
    return chunks
