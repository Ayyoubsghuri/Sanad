"""BO auto-update: append to a pack, discovery, download, the whole job (fake SGG + stub extractor), provider routes."""
from __future__ import annotations

import shutil
import sqlite3
import sys
import textwrap
import time
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from legalrag.bo_update import discover
from legalrag.bo_update.runner import BoUpdater
from legalrag.builder.append import AppendError, append_sources
from legalrag.builder.from_bo import bo_to_sources
from legalrag.config import Settings
from legalrag.main import create_app
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.state import build_context
from legalrag.store.lawpack import LawPack
from legalrag.store.signing import verify_pack

from conftest import H, TOKEN
from test_from_bo import BO_MD

HEADER_NEW = "عدد 7499 - 5 جمادى الأولى 1447 (27 أكتوبر 2025)\n\n"
PDF = b"%PDF-1.4\n" + b"x" * 500


def _md(tmp: Path, number: str = "7499") -> Path:
    p = tmp / f"BO_{number}_Ar.md"
    p.write_text(HEADER_NEW.replace("7499", number) + BO_MD, "utf-8")
    return p


def test_append_adds_text_and_is_idempotent(tmp_path, pack_path):
    work = tmp_path / "w.db"
    shutil.copy2(pack_path, work)
    before = LawPack(work)
    n_chunks = before._one("SELECT COUNT(*) n FROM chunk")["n"]
    before.close()
    src, _ = bo_to_sources([_md(tmp_path)])
    res = append_sources(work, src, HashingEmbedder(), "append-1")
    assert res["articles"] >= 4 and res["chunks"] >= 4
    p = LawPack(work)
    assert p._one("SELECT COUNT(*) n FROM chunk")["n"] == n_chunks + res["chunks"]
    assert p._one("SELECT COUNT(*) n FROM chunk_embedding")["n"] >= res["chunks"]
    # the new text is findable through the keyword index and has a vector
    hits = p.keyword_search("تجربه", date(2030, 1, 1), 5)  # keyword index stores normalised terms
    assert hits
    assert p.version == "append-1"
    idx = p.vector_index("hash-ngram-v1")
    assert idx is not None and len(idx.ids) >= res["chunks"]
    p.close()


def test_append_refuses_a_different_embedder(tmp_path, pack_path):
    work = tmp_path / "w.db"
    shutil.copy2(pack_path, work)
    src, _ = bo_to_sources([_md(tmp_path)])
    with pytest.raises(AppendError, match="same model"):
        append_sources(work, src, HashingEmbedder("other-model"), "x")


def test_append_signs_when_given_a_key(tmp_path, pack_path, keys):
    work = tmp_path / "w.db"
    shutil.copy2(pack_path, work)
    src, _ = bo_to_sources([_md(tmp_path)])
    append_sources(work, src, HashingEmbedder(), "signed-1", keys[0])
    assert verify_pack(work, keys[1]).ok


def test_same_instrument_again_is_kept_next_to_the_old_one(tmp_path, pack_path):
    work = tmp_path / "w.db"
    shutil.copy2(pack_path, work)
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    s1, _ = bo_to_sources([_md(a, "7499")])
    append_sources(work, s1, HashingEmbedder(), "v1")
    s2, _ = bo_to_sources([_md(b, "7500")])  # same texts republished in another issue
    res = append_sources(work, s2, HashingEmbedder(), "v2")
    assert res["renamed"] and res["articles"] >= 4
    db = sqlite3.connect(work)
    assert db.execute("SELECT COUNT(*) FROM instrument WHERE instrument_id LIKE 'DAHIR_1.25.67%'").fetchone()[0] == 2


# ---------------------------------------------------------------------------------------------------- discovery
def _fake_sgg(existing: set[str]):
    def handler(req: httpx.Request) -> httpx.Response:
        name = req.url.path.rsplit("/", 1)[-1]
        if name in existing:
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf", "content-length": str(len(PDF))})
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_probe_finds_the_next_issues_and_stops(tmp_path):
    s = Settings(data_dir=tmp_path, bo_url_template="https://sgg.example/BO/{year}/BO_{num}_Ar.pdf")
    client = _fake_sgg({"BO_7499_Ar.pdf", "BO_7499-bis_Ar.pdf", "BO_7501_Ar.pdf"})
    got = discover.discover(s, {(7498, "")}, client=client)
    assert [c.key for c in got] == ["7499", "7499-bis", "7501"]


def test_listing_page_links_are_read(tmp_path):
    html = '<a href="/BO/AR/9/2026/BO_7510_Ar.PDF">x</a> <a href="BO_7511-bis_Ar.pdf">y</a> <a href="other.pdf">z</a>'
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html)))
    s = Settings(data_dir=tmp_path, bo_url_template="", bo_listing_urls=["https://sgg.example/list"])
    got = discover.discover(s, set(), client=client)
    assert {c.key for c in got} == {"7510", "7511-bis"}
    assert got[0].url.startswith("https://sgg.example/")


def test_download_checks_pdf_header_and_size(tmp_path):
    c = discover.Candidate("BO_1_Ar", 1, "", "https://x/BO_1_Ar.pdf")
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=PDF, headers={"content-length": str(len(PDF))})))
    p, sha = discover.download(c, tmp_path, 5, 5, client=ok)
    assert p.read_bytes() == PDF and len(sha) == 64
    html = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>login</html>")))
    with pytest.raises(ValueError, match="not return a PDF"):
        discover.download(c, tmp_path / "2", 5, 5, client=html)
    assert not list((tmp_path / "2").glob("*.pdf"))
    big = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=PDF + b"y" * (2 << 20))))
    with pytest.raises(ValueError, match="larger than 1 MB"):
        discover.download(c, tmp_path / "3", 1, 5, client=big)


# ---------------------------------------------------------------------------------------------------- the whole job
STUB_EXTRACTOR = textwrap.dedent('''
    import sys
    from pathlib import Path
    pdf = Path(sys.argv[1]); out = Path(sys.argv[sys.argv.index("-o") + 1])
    num = pdf.stem.split("_")[1]
    Path(str(out) + ".md").write_text(open(__file__.replace("extract_bo_pdf.py", "body.md"), encoding="utf-8").read().replace("NNNN", num), encoding="utf-8")
    print("font repair: 0 Sakkal fonts", file=sys.stderr)
''')


@pytest.fixture()
def job_env(tmp_path, pack_path, keys, monkeypatch):
    pipe = tmp_path / "pipe"; pipe.mkdir()
    (pipe / "extract_bo_pdf.py").write_text(STUB_EXTRACTOR)
    (pipe / "body.md").write_text("عدد NNNN - 5 جمادى الأولى 1447 (27 أكتوبر 2025)\n\n" + BO_MD, "utf-8")
    s = Settings(data_dir=tmp_path / "data", lawpack_path=tmp_path / "pack" / "current.db", lawpack_public_key_hex=keys[1], api_token=TOKEN, ner_enabled=False,
                 bo_pipeline_dir=pipe, bo_url_template="https://sgg.example/BO/{year}/BO_{num}_Ar.pdf", pack_private_key_hex=keys[0],
                 embedder_local_kind="hash", default_mode="hybrid")
    (tmp_path / "pack").mkdir()
    shutil.copy2(pack_path, s.lawpack_path)
    db = sqlite3.connect(s.lawpack_path)  # the fixture's synthetic BO numbers (9999...) would look like "newest issue": neutralise them, re-sign
    db.execute("UPDATE instrument SET bo_number=NULL WHERE CAST(bo_number AS INTEGER) NOT BETWEEN 7000 AND 7497"); db.commit(); db.close()
    from legalrag.store.signing import sign_pack
    sign_pack(s.lawpack_path, keys[0], "2026-10-20T00:00:00+00:00", "fixture-test")
    c = build_context(s)
    assert c.pack_usable(), c.pack_error
    seed = s.resolved_bo_dir() / "pdfs"; seed.mkdir(parents=True)
    (seed / "BO_7498_Ar.pdf").write_bytes(PDF)  # newest issue we already have (finished by an earlier update)
    discover.mark_done(s.resolved_bo_dir(), [(7498, "")], 1, "2026-10-20T00:00:00+00:00")
    fake = _fake_sgg({"BO_7499_Ar.pdf"})
    monkeypatch.setattr(discover.httpx, "Client", lambda *a, **k: fake)
    yield c
    c.close()


def _wait(u: BoUpdater, timeout=60):
    t0 = time.time()
    while u.job.state in ("queued", "running") and time.time() - t0 < timeout:
        time.sleep(0.05)
    return u.job


def test_job_downloads_extracts_indexes_and_installs(job_env):
    c = job_env
    old_version = c.pack.version
    u = BoUpdater(c)
    assert u.problems() == []
    job = u.start()
    _wait(u)
    d = job.to_dict()
    assert d["state"] == "done", d
    assert [s["status"] for s in d["steps"]] == ["done"] * 5
    assert d["progress"] == 1.0
    assert d["added"]["articles"] >= 4 and d["found"][0]["name"] == "BO_7499_Ar"
    assert c.pack.version != old_version and c.pack_usable()
    assert c.pack.meta.get("last_bo_check")
    assert not (c.settings.resolved_lawpack_path().with_name("previous.db")).exists()  # one pack on disk
    # run again: nothing new, nothing changes
    again = u.start(); _wait(u)
    assert again.to_dict()["state"] == "done" and again.to_dict()["added"] == {}


def test_dry_run_downloads_nothing(job_env):
    u = BoUpdater(job_env)
    j = u.start(dry_run=True); _wait(u)
    assert j.state == "done" and len(j.found) == 1
    assert not (job_env.settings.resolved_bo_dir() / "pdfs" / "BO_7499_Ar.pdf").exists()


def test_signed_pack_without_key_is_refused_up_front(job_env):
    job_env.settings.pack_private_key_hex = None
    assert any("signed" in p for p in BoUpdater(job_env).problems())


def test_offline_mode_refuses(job_env):
    job_env.db.set_settings({"mode": "offline"})
    assert any("offline" in p for p in BoUpdater(job_env).problems())


def test_api_routes(job_env):
    client = TestClient(create_app(job_env.settings, job_env))
    st = client.get("/v1/bo/status", headers=H).json()
    assert st["problems"] == [] and st["newest_local"] == 7498
    r = client.post("/v1/bo/update", json={}, headers=H)
    assert r.status_code == 202
    t0 = time.time()
    while time.time() - t0 < 60:
        j = client.get("/v1/bo/update", headers=H).json()
        if j["state"] != "running" and j["state"] != "queued":
            break
        time.sleep(0.05)
    assert j["state"] == "done", j
    assert client.post("/v1/bo/update", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401


# ---------------------------------------------------------------------------------------------------- providers
def test_providers_save_activate_and_never_return_the_key(client, ctx):
    r = client.put("/v1/llm-providers/openai-main", headers=H, json={"kind": "openai", "label": "OpenAI", "model": "gpt-4o", "api_key": "sk-test-1234567890"})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] == "openai-main" and body["providers"][0]["has_key"] is True
    assert "sk-test" not in r.text
    assert ctx.keys.get_secret("llm_p_openai-main") == "sk-test-1234567890"
    llm = ctx.llm()
    assert llm is not None and llm.model == "gpt-4o" and llm.name == "openai" and llm.base == "https://api.openai.com/v1"
    r = client.put("/v1/llm-providers/claude", headers=H, json={"kind": "anthropic", "label": "Anthropic", "model": "claude-x", "api_key": "sk-ant-1234567890"})
    assert r.status_code == 200 and len(r.json()["providers"]) == 2
    assert client.post("/v1/llm-providers/active", headers=H, json={"id": "claude"}).json()["active"] == "claude"
    assert ctx.llm().name == "anthropic"
    client.post("/v1/llm-providers/checker", headers=H, json={"id": "openai-main"})
    assert ctx.claim_checker().name.startswith("llm:openai")
    assert client.delete("/v1/llm-providers/claude", headers=H).status_code == 204
    st = client.get("/v1/llm-providers", headers=H).json()
    assert st["active"] is None and ctx.keys.get_secret("llm_p_claude") is None


def test_provider_validation(client):
    assert client.put("/v1/llm-providers/x", headers=H, json={"kind": "openai", "label": "a", "model": "m"}).status_code == 422  # new provider needs a key
    assert client.put("/v1/llm-providers/x", headers=H, json={"kind": "openai_compat", "label": "a", "model": "m"}).status_code == 422  # needs a base URL
    assert client.put("/v1/llm-providers/Bad Id", headers=H, json={"kind": "openai", "label": "a", "model": "m", "api_key": "12345678"}).status_code in (404, 422)
    assert client.put("/v1/llm-providers/local", headers=H, json={"kind": "openai_compat", "label": "Local", "model": "qwen", "base_url": "http://127.0.0.1:1234/v1"}).status_code == 200


def test_offline_mode_hides_the_provider(client, ctx):
    client.put("/v1/llm-providers/o", headers=H, json={"kind": "openai", "label": "O", "model": "gpt-4o", "api_key": "sk-test-1234567890"})
    ctx.db.set_settings({"mode": "offline"})
    assert ctx.llm() is None
    assert client.post("/v1/llm-providers/o/test", headers=H).json()["ok"] is False


def test_a_pdf_left_by_an_interrupted_run_is_processed_not_mistaken_for_done(job_env, monkeypatch):
    """The first run downloaded BO 7499 and stopped before installing it; the next check used to say "no new issue" forever."""
    c = job_env
    seed = c.settings.resolved_bo_dir() / "pdfs"
    (seed / "BO_7499_Ar.pdf").write_bytes(PDF)
    empty_site = _fake_sgg(set())  # the site lists nothing new, or is unreachable
    monkeypatch.setattr(discover.httpx, "Client", lambda *a, **k: empty_site)
    u = BoUpdater(c)
    assert u.status()["pending_local"] == 1 and u.status()["newest_local"] == 7498
    job = u.start(); _wait(u)
    d = job.to_dict()
    assert d["state"] == "done" and d["added"]["articles"] >= 4, (d.get("error"), d.get("warnings"), d)
    assert [x["name"] for x in d["found"]] == ["BO_7499_Ar"]  # taken from the folder, not fetched again
    again = u.start(); _wait(u)
    assert again.to_dict()["added"] == {} and u.status()["pending_local"] == 0 and u.status()["newest_local"] == 7499


def test_an_issue_without_legal_text_is_finished_not_new_again(tmp_path):
    from legalrag.bo_update import discover
    root = tmp_path
    (root / "pdfs").mkdir()
    (root / "pdfs" / "BO_7600_Ar.pdf").write_bytes(PDF)
    done, known, pending = discover.issue_state(root, ["7500"])
    assert [c.name for c in pending] == ["BO_7600_Ar"] and (7600, "") not in known
    discover.mark_done(root, [(7600, "")], 0, "now")
    done, known, pending = discover.issue_state(root, ["7500"])
    assert pending == [] and (7600, "") in done
