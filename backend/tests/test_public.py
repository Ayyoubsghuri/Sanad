"""Public mode (a shared server): nothing about visitors is stored, only their routes are open, questions are limited."""
from datetime import date

from fastapi.testclient import TestClient

from legalrag.config import Settings
from legalrag.llm.providers import ScriptedProvider
from legalrag.main import create_app
from legalrag.state import build_context
from test_pipeline import faithful

KEY = "k" * 24


def _client(tmp_path, pack_path, keys, **kw):
    s = Settings(data_dir=tmp_path / "d", lawpack_path=pack_path, lawpack_public_key_hex=keys[1], ner_enabled=False, query_rewrite=False,
                 public_mode=True, public_api_keys=f"demo-site:{KEY}", **kw)
    c = build_context(s)
    c.today_fn = lambda: date(2026, 10, 27)
    c.llm_override = ScriptedProvider(faithful)
    return s, c, TestClient(create_app(s, c))


def _ask(cl, q="Quelle est la durée de la période d'essai ?", ip="203.0.113.7"):
    h = {"X-Forwarded-For": f"1.2.3.4, {ip}"}
    p = cl.post("/v1/queries", json={"question": q, "as_of": "2026-01-01", "session_id": "chat-1"}, headers=h)
    if p.status_code != 201:
        return p, None
    return p, cl.post(f"/v1/queries/{p.json()['query_id']}/run", json={}, headers=h)


def test_public_mode_stores_nothing_and_opens_only_the_visitors_routes(tmp_path, pack_path, keys):
    s, c, cl = _client(tmp_path, pack_path, keys)
    try:
        assert cl.get("/health").json()["public"] is True
        assert cl.post("/pair", headers={"Origin": "https://someone.example"}).json() == {"token": "public"}
        # closed: keys, settings changes, updates, logs, traces, documents, the toolkit, model installs
        for m, path in [("GET", "/v1/llm-providers"), ("PUT", "/v1/llm-providers/x"), ("GET", "/v1/outbound-log"), ("GET", "/v1/traces"),
                        ("POST", "/v1/pack/update"), ("POST", "/v1/bo/update"), ("POST", "/v1/documents"), ("POST", "/v1/pro/jobs"),
                        ("POST", "/v1/compute/install"), ("GET", "/v1/compute"), ("PUT", "/v1/secrets/llm_main"), ("GET", "/v1/cases")]:
            assert cl.request(m, path).status_code == 403, path
        before = cl.get("/v1/settings").json()["mode"]
        assert cl.patch("/v1/settings", json={"mode": "offline"}).json()["mode"] == before        # a visitor changes nothing
        p, r = _ask(cl)
        assert p.status_code == 201 and r.status_code == 200 and r.json()["status"] in ("answered", "partial")
        # nothing about the question is left on the server
        assert c.db.path.name == ":memory:" and not list(tmp_path.glob("**/user.db"))
        for table in ("legal_case", "vault_entry", "pending_query", "trace", "coverage_gap"):
            assert c.db.one(f"SELECT COUNT(*) AS n FROM {table}")["n"] == 0, table
        assert all(row["payload"] is None and row["case_id"] is None for row in c.db.list_outbound())
        from legalrag.pipeline.memory import get_memory
        assert not get_memory().context("chat-1", [])                                            # no server-side chat memory
    finally:
        c.close()


def test_public_limits_per_visitor_and_api_keys(tmp_path, pack_path, keys):
    s, c, cl = _client(tmp_path, pack_path, keys, public_per_hour=2, public_per_day=5)
    try:
        assert _ask(cl, ip="198.51.100.1")[0].status_code == 201
        assert _ask(cl, ip="198.51.100.1")[0].status_code == 201
        p, _ = _ask(cl, ip="198.51.100.1")
        assert p.status_code == 429 and int(p.headers["Retry-After"]) > 0                          # third in the hour: refused
        assert _ask(cl, ip="198.51.100.2")[0].status_code == 201                                   # another visitor is not affected
        # the public API: a key is required; the reply holds the statements and the articles they rest on
        assert cl.post("/v1/public/ask", json={"question": "Quelle est la durée de la période d'essai ?"}).status_code == 401
        r = cl.post("/v1/public/ask", json={"question": "Quelle est la durée de la période d'essai ?", "as_of": "2026-01-01"}, headers={"X-Api-Key": KEY})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["answer"] and {x for c_ in a["answer"] for x in c_["sources"]} <= {s_["id"] for s_ in a["sources"]}
        assert c.db.one("SELECT COUNT(*) AS n FROM legal_case")["n"] == 0
        assert cl.options("/v1/public/ask", headers={"Origin": "https://other-site.example", "Access-Control-Request-Method": "POST"}).status_code == 200
    finally:
        c.close()
