"""Search by meaning through Cloudflare Workers AI instead of local models: settings, the privacy gateway, Offline mode."""
import json

import httpx
import numpy as np
from fastapi.testclient import TestClient

from legalrag.config import Settings
from legalrag.main import create_app
from legalrag.retrieval.embedders import CloudflareEmbedder
from legalrag.retrieval.rerankers import LexicalReranker
from legalrag.state import build_context

H = {"Authorization": "Bearer test-token"}
ACCT = "0123456789abcdef0123456789abcdef"


def test_cloudflare_embeddings_choice_gateway_and_offline(tmp_path, pack_path, keys, monkeypatch):
    sent = []

    def handler(request: httpx.Request):
        sent.append((request.url.host, request.url.path, json.loads(request.content), request.headers.get("authorization")))
        n = len(json.loads(request.content)["text"])
        return httpx.Response(200, json={"success": True, "result": {"shape": [n, 1024], "data": [[0.5] * 1024 for _ in range(n)]}})

    s = Settings(data_dir=tmp_path / "d", lawpack_path=pack_path, lawpack_public_key_hex=keys[1], api_token="test-token", ner_enabled=False,
                 query_rewrite=False, embeddings_source="cloudflare")
    c = build_context(s, transport=httpx.MockTransport(handler))
    try:
        cl = TestClient(create_app(s, c))
        monkeypatch.setattr(type(c), "pack_embedder_id", lambda self: "bge-m3")   # the real pack holds bge-m3 vectors
        v = cl.get("/v1/compute", headers=H).json()
        assert v["source"] == "cloudflare" and not v["cloudflare_ready"] and v["ram_gb"]
        assert c.embedder() is None and isinstance(c.reranker(), LexicalReranker)       # no account yet: keyword search, no local models

        assert cl.post("/v1/compute", headers=H, json={"account": "nope"}).status_code == 422
        assert cl.post("/v1/compute", headers=H, json={"source": "local"}).status_code == 409   # models not installed
        v = cl.post("/v1/compute", headers=H, json={"account": ACCT, "token": "t" * 40}).json()
        assert v["cloudflare_ready"] and "t" * 40 not in json.dumps(v)                        # the token is never sent back

        c.db.set_settings({"mode": "hybrid"})
        emb = c.embedder()
        assert isinstance(emb, CloudflareEmbedder)
        vec = emb.embed(["سؤال [PERSON_1]"])
        assert vec.shape == (1, 1024) and abs(float(np.linalg.norm(vec[0])) - 1) < 1e-5
        host, path, body, auth = sent[-1]
        assert host == "api.cloudflare.com" and path == f"/client/v4/accounts/{ACCT}/ai/run/@cf/baai/bge-m3" and auth == "Bearer " + "t" * 40
        assert any(e["kind"] == "embed" and e["host"] == "api.cloudflare.com" for e in c.db.list_outbound())   # in the outbound log
        assert cl.post("/v1/compute/test", headers=H).json() == {"ok": True, "dimensions": 1024}

        c.db.set_settings({"mode": "offline"})
        n = len(sent)
        assert c.embedder() is None and len(sent) == n                                         # Offline: nothing is sent
        assert cl.post("/v1/compute/test", headers=H).status_code == 409
    finally:
        c.close()
