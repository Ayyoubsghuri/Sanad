"""Professional toolkit: masking, sources only from the pack and the rulings db, invented citations dropped, names restored."""
import json
import sqlite3
import time

from legalrag.llm.providers import GenRequest, ScriptedProvider
from legalrag.pro import catalog as C
from legalrag.pro.rulings import open_store

H = {"Authorization": "Bearer test-token"}

FACTS = ("M. Ahmed Benali, CIN BK123456, a été licencié par son employeur sans préavis après huit ans de travail. "
         "Il demande une indemnité pour licenciement abusif.")


def make_rulings(ctx):
    d = ctx.settings.data_dir / "rulings"
    d.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(d / "rulings.db")
    db.executescript("""
CREATE TABLE ruling (ruling_id TEXT PRIMARY KEY, source_size INTEGER, number TEXT, decision_date TEXT, file_number TEXT, chamber TEXT, case_type TEXT,
  keywords TEXT, principle TEXT, facts TEXT, grounds_json TEXT, verdict TEXT, outcome TEXT, petitioner_won INTEGER, articles_json TEXT,
  text_quality REAL, ocr INTEGER, warnings_json TEXT, full_text TEXT);
CREATE VIRTUAL TABLE ruling_fts USING fts5(ruling_id UNINDEXED, keywords, principle, facts, grounds, verdict, tokenize='unicode61');
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);""")
    rows = [
        ("101", "1/50", "2024-01-10", "social", "طرد تعسفي - التعويض عن الطرد - الإخطار", "الأجير المطرود دون إخطار يستحق التعويض",
         [{"ground": "خرق مقتضيات الإخطار", "answer": "حيث صح ما عابه الطاعن", "accepted": True}], "cassation", 1),
        ("102", "1/51", "2023-05-02", "social", "طرد تعسفي - خطأ جسيم - إثبات", "إثبات الخطأ الجسيم على المشغل",
         [{"ground": "انعدام التعليل", "answer": "لكن المحكمة عللت قرارها", "accepted": False}], "rejected", 0),
        ("103", "1/52", "2022-02-02", "family", "نفقة - حضانة", "النفقة على الأب", [], "rejected", 0),
    ]
    for rid, num, dt, ch, kw, pr, gr, oc, won in rows:
        db.execute("INSERT INTO ruling VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (rid, 1, num, dt, "2023/1/5/1", ch, ch, kw, pr, "حيث يستفاد من وثائق الملف أن الأجير طرد", json.dumps(gr, ensure_ascii=False),
                    "قضت المحكمة", oc, won, "[]", 0.95, 0, "[]", "نص"))
        db.execute("INSERT INTO ruling_fts VALUES (?,?,?,?,?,?)", (rid, kw, pr, "الأجير طرد", " ".join(g["ground"] for g in gr), ""))
    db.commit()
    db.close()


def wait(client, jid):
    for _ in range(200):
        j = client.get(f"/v1/pro/jobs/{jid}", headers=H).json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_catalog_lists_every_profession(client):
    c = client.get("/v1/pro/catalog", headers=H).json()
    groups = {t["group"] for t in c["tools"]}
    assert {"featured", "lawyer", "judge", "notary", "corporate", "bailiff"} <= groups
    assert all("instructions" not in t for t in c["tools"])
    assert {t["id"] for t in c["tools"] if t["featured"]} == {"courtroom", "case_analyzer", "jurisprudence"}


def test_rulings_search_ranks_by_subject(ctx):
    make_rulings(ctx)
    st = open_store(ctx.settings.data_dir)
    got = st.search("التعويض عن الطرد التعسفي للأجير دون إخطار", k=3)
    assert got and got[0]["ruling_id"] == "101" and got[0]["petitioner_won"] is True
    assert all(r["chamber"] == "social" for r in st.search("الطرد", k=5, chamber="social"))


def test_courtroom_masks_cites_only_given_sources_and_restores(client, ctx):
    make_rulings(ctx)
    seen: list[GenRequest] = []

    def script(req: GenRequest):
        seen.append(req)
        if req.kind == "pro_plan":
            return {"issues": ["الطرد التعسفي"], "queries": ["التعويض عن الطرد التعسفي"], "chamber": "social", "summary": "طرد"}
        ids = [p["id"] for p in req.payload["passages"]] + [r["id"] for r in req.payload["rulings"]]
        if req.kind == "pro_lawyer_a":
            return {"position": "[PERSON_1] a droit à une indemnité", "arguments": [
                {"title": "Absence de préavis", "argument": "Le préavis est obligatoire.", "sources": [ids[0], "S99"], "strength": "strong"}]}
        if req.kind == "pro_lawyer_b":
            assert req.payload["lawyer_a"]["arguments"]
            return {"position": "faute grave", "rebuttals": [{"target": 1, "rebuttal": "Faute grave alléguée", "sources": ["R2"]}], "counter_arguments": []}
        assert req.kind == "pro_judge" and "similar_rulings_outcomes" in req.payload
        return {"issues": [{"issue": "Préavis", "finding": "Favorable", "favours": "A", "sources": [ids[0]]}], "verdict": "Indemnité probable",
                "chance_of_success": 100, "confidence": "medium", "chance_reasoning": "…", "risks": [{"risk": "Preuve", "sources": []}],
                "recommendations": ["Réunir les bulletins de paie"]}

    ctx.llm_override = ScriptedProvider(script)
    prep = client.post("/v1/pro/jobs", headers=H, json={"tool": "courtroom", "fields": {"facts": FACTS, "side": "claimant"}, "lang": "fr"})
    assert prep.status_code == 201, prep.text
    p = prep.json()
    sent = p["preview"][0]["text"]
    assert "Benali" not in sent and "BK123456" not in sent and p["planned_calls"] == 4
    assert client.post(f"/v1/pro/jobs/{p['job_id']}/run", headers=H, json={}).status_code == 200
    j = wait(client, p["job_id"])
    assert j["status"] == "done", j.get("error")
    for req in seen:   # nothing private ever went out
        assert "Benali" not in json.dumps(req.payload, ensure_ascii=False)
    r = j["result"]
    out = r["output"]
    arg = out["lawyer_a"]["arguments"][0]
    assert "S99" not in arg["sources"] and arg["sources"] and r["unsupported_citations"] == 1
    assert "Ahmed Benali" in out["lawyer_a"]["position"]          # restored on the device
    assert out["judge"]["chance_of_success"] == 95                # an estimate, never certain
    assert out["judge"]["risks"][0]["unsourced"] is True
    assert r["rulings"] and r["rulings"][0]["chamber"] == "social"
    assert [s["id"] for s in j["steps"]] == ["plan", "law", "rulings", "lawyer_a", "lawyer_b", "judge", "check"]


def test_without_model_returns_sources_only(client, ctx):
    make_rulings(ctx)
    ctx.llm_override = None
    p = client.post("/v1/pro/jobs", headers=H, json={"tool": "jurisprudence", "fields": {"facts": "التعويض عن الطرد التعسفي"}}).json()
    assert p["planned_calls"] == 0
    client.post(f"/v1/pro/jobs/{p['job_id']}/run", headers=H, json={})
    j = wait(client, p["job_id"])
    assert j["status"] == "done" and j["result"]["status"] == "sources_only" and j["result"]["rulings"]
    assert "no_model" in j["result"]["warnings"]


def test_report_tool_and_missing_field(client, ctx):
    assert client.post("/v1/pro/jobs", headers=H, json={"tool": "contract_review", "fields": {}}).status_code == 422
    assert client.post("/v1/pro/jobs", headers=H, json={"tool": "nope", "fields": {}}).status_code == 404

    def script(req):
        if req.kind == "pro_plan":
            return {"issues": ["عقد"], "queries": ["التعويض عن الطرد التعسفي"]}
        assert not req.payload["rulings"]          # contract review does not search rulings
        ids = [p["id"] for p in req.payload["passages"]]
        return {"title": "Revue", "summary": "…", "sections": [{"heading": "Clauses risquées", "items": [
            {"text": "Clause de non-concurrence trop large", "sources": ids[:1] + ["R7"], "tag": "risk"}]}]}

    ctx.llm_override = ScriptedProvider(script)
    p = client.post("/v1/pro/jobs", headers=H, json={"tool": "contract_review", "fields": {"document": "Contrat de travail entre X et Y"}}).json()
    client.post(f"/v1/pro/jobs/{p['job_id']}/run", headers=H, json={})
    j = wait(client, p["job_id"])
    assert j["status"] == "done", j.get("error")
    it = j["result"]["output"]["sections"][0]["items"][0]
    assert "R7" not in it["sources"]


def test_catalog_tools_have_complete_labels():
    for t in C.TOOLS:
        assert t["label"]["ar"] and t["label"]["fr"] and t["description"]["ar"]
        if t["kind"] != "courtroom":
            assert t["instructions"] and t["sections"]


def test_phone_copy_of_the_toolkit_is_current():
    """The Android app runs the same tools from mobile/android/web-extra/pro_toolkit.json: regenerate it after changing
    the catalog or the prompts (python -m legalrag.pro.export)."""
    from pathlib import Path

    from legalrag.pro import export

    f = Path(__file__).resolve().parents[2] / "mobile/android/web-extra/pro_toolkit.json"
    assert f.read_text(encoding="utf-8") == export.text()


def test_gateway_allows_the_toolkit_in_hybrid_and_local_models_offline(ctx):
    """Every call kind the app makes must pass the Hybrid mode check, and a model on this computer works in Offline mode."""
    from legalrag.privacy.gateway import MODE_ALLOWS, is_local_url

    ctx.db.set_settings({"mode": "hybrid"})
    for kind in ("guide", "contract_check", "pro_plan", "pro_lawyer_a", "pro_judge", "pro_write", "generate"):
        assert ctx.gateway.allowed(kind), kind
    ctx.db.set_settings({"mode": "offline"})
    assert not ctx.gateway.allowed("pro_plan") and not MODE_ALLOWS["offline"]
    assert is_local_url("http://127.0.0.1:11434/v1") and is_local_url("http://localhost:1234/v1") and not is_local_url("https://api.openai.com/v1")


def test_offline_mode_uses_only_a_local_model(client, ctx):
    ctx.llm_override = None
    r = client.put("/v1/llm-providers/cloud", headers=H, json={"kind": "openai", "label": "OpenAI", "model": "gpt-4o", "api_key": "sk-test-key-123"})
    assert r.status_code == 200
    assert client.put("/v1/llm-providers/mine", headers=H, json={"kind": "local", "label": "Ollama", "model": "qwen2.5:7b",
                                                                     "base_url": "https://example.com/v1"}).status_code == 422
    assert client.put("/v1/llm-providers/mine", headers=H, json={"kind": "local", "label": "Ollama", "model": "qwen2.5:7b"}).status_code == 200
    assert client.post("/v1/llm-providers/offline", headers=H, json={"id": "cloud"}).status_code == 422
    ctx.db.set_settings({"mode": "offline"})
    assert ctx.llm() is None                       # the active provider is the cloud one: Offline mode gives no model
    v = client.post("/v1/llm-providers/offline", headers=H, json={"id": "mine"}).json()
    assert v["offline"] == "mine"
    prov = ctx.llm()
    assert prov is not None and prov.name == "local" and prov.base.startswith("http://127.0.0.1:11434")
    ctx.db.set_settings({"mode": "hybrid"})
    assert ctx.llm().name == "openai"             # Hybrid keeps the cloud model
    assert client.get("/v1/llm-providers/local-models?base_url=https://api.openai.com/v1", headers=H).status_code == 422
    got = client.get("/v1/llm-providers/local-models?base_url=http://127.0.0.1:9/v1", headers=H).json()
    assert got["ok"] is False and got["models"] == []


def _fake_model_server(seen):
    """An OpenAI-compatible server (cloud or Ollama) answering every structured call of the toolkit."""
    import httpx

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen.append((request.url.host, body["messages"][0]["content"][:40]))
        props = body["response_format"]["json_schema"]["schema"]["properties"]
        if "queries" in props:
            out = {"issues": ["طرد"], "queries": ["التعويض عن الطرد التعسفي"]}
        elif "chance_of_success" in props:
            out = {"issues": [], "verdict": "v", "chance_of_success": 60, "confidence": "low", "chance_reasoning": "r", "risks": [], "recommendations": []}
        elif "rebuttals" in props:
            out = {"position": "b", "rebuttals": [], "counter_arguments": []}
        else:
            out = {"position": "a", "arguments": [{"title": "t", "argument": "x", "sources": ["S1"], "strength": "strong"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}}]})

    return httpx.MockTransport(handler)


def _run_courtroom(client):
    p = client.post("/v1/pro/jobs", headers=H, json={"tool": "courtroom", "fields": {"facts": FACTS, "side": "claimant"}}).json()
    client.post(f"/v1/pro/jobs/{p['job_id']}/run", headers=H, json={})
    return p, wait(client, p["job_id"])


def test_toolkit_through_the_real_gateway_hybrid_cloud_and_offline_local(tmp_path, pack_path, keys):
    from fastapi.testclient import TestClient

    from legalrag.config import Settings
    from legalrag.main import create_app
    from legalrag.state import build_context

    seen: list = []
    s = Settings(data_dir=tmp_path / "d", lawpack_path=pack_path, lawpack_public_key_hex=keys[1], api_token="test-token", ner_enabled=False, query_rewrite=False)
    c = build_context(s, transport=_fake_model_server(seen))
    try:
        cl = TestClient(create_app(s, c))
        cl.put("/v1/llm-providers/cloud", headers=H, json={"kind": "openai_compat", "label": "Cloud", "model": "m", "base_url": "https://api.example.com/v1"})
        cl.put("/v1/llm-providers/mine", headers=H, json={"kind": "local", "label": "Ollama", "model": "qwen2.5:7b"})
        cl.post("/v1/llm-providers/active", headers=H, json={"id": "cloud"})
        cl.post("/v1/llm-providers/offline", headers=H, json={"id": "mine"})

        c.db.set_settings({"mode": "hybrid"})
        p, j = _run_courtroom(cl)
        assert j["status"] == "done", j.get("error")        # the pro_* calls pass the Hybrid mode check
        assert {h for h, _ in seen} == {"api.example.com"} and len(seen) == 4

        seen.clear()
        c.db.set_settings({"mode": "offline"})
        p, j = _run_courtroom(cl)
        assert p["planned_calls"] == 4 and j["status"] == "done", j.get("error")
        assert {h for h, _ in seen} == {"127.0.0.1"}        # Offline: only the model on this computer
        assert j["result"]["output"]["judge"]["chance_of_success"] == 60
    finally:
        c.close()


def test_rulings_download_installs_only_a_matching_file(client, ctx, monkeypatch, tmp_path):
    import hashlib

    import httpx

    from legalrag.pro import rulings_update as RU
    from legalrag.pro.rulings import installed_version, open_store

    src = tmp_path / "pub"
    src.mkdir()
    ctx_dir = ctx.settings.data_dir
    make_rulings(ctx)                                      # build a db in the data dir, then move it to the "server"
    db_bytes = (ctx_dir / "rulings" / "rulings.db").read_bytes()
    (ctx_dir / "rulings" / "rulings.db").unlink()
    good = {"version": "2026.11.20.1200", "db_url": "https://hf.example/rulings.db", "size_bytes": len(db_bytes),
            "sha256": hashlib.sha256(db_bytes).hexdigest(), "rulings": 3}
    manifest = dict(good)

    def handler(req: httpx.Request):
        if req.url.path.endswith("manifest.json"):
            return httpx.Response(200, json=manifest)
        return httpx.Response(200, content=db_bytes)

    real = httpx.Client
    monkeypatch.setattr(RU.httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    ctx.db.set_settings({"mode": "hybrid"})
    RU._UPDATERS.clear()

    chk = client.get("/v1/pro/rulings/update", headers=H).json()
    assert chk["installed_version"] is None and chk["update_available"] is True and chk["rulings"] == 3

    def run():
        client.post("/v1/pro/rulings/update", headers=H)
        for _ in range(200):
            j = client.get("/v1/pro/rulings/update/job", headers=H).json()
            if j["state"] in ("done", "error", "cancelled"):
                return j
            time.sleep(0.05)

    manifest["sha256"] = "0" * 64                          # a damaged download is refused
    assert run()["state"] == "error" and installed_version(ctx_dir) is None
    manifest.update(good)
    j = run()
    assert j["state"] == "done", j
    assert (ctx_dir / "rulings" / "current.txt").read_text() == "rulings-2026.11.20.1200.db"
    assert open_store(ctx_dir).stats()["total"] == 3
    assert client.get("/v1/pro/catalog", headers=H).json()["rulings_available"] is True
    ctx.db.set_settings({"mode": "offline"})
    assert client.post("/v1/pro/rulings/update", headers=H).status_code == 409
