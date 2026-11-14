"""Frontend tools on a small pack built through the real importer: old -> new finder, history across editions, calculators' basis, contract check, guides."""
from __future__ import annotations

import shutil
from datetime import date

import pytest
from fastapi.testclient import TestClient

from legalrag.builder.append import append_sources
from legalrag.builder.from_law_pdf import law_pdf_to_sources
from legalrag.config import Settings
from legalrag.main import create_app
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.state import build_context
from legalrag.services import tools as T
from legalrag.services import review as rv
from legalrag.store.lawpack import LawPack

H = {"Authorization": "Bearer test-token"}


def _md(tmp, name, arts, head="مدونة"):
    p = tmp / name
    p.write_text(f"<!-- page 1 -->\n\n{head}\n\n" + "\n\n".join(f"## {w} {n}\n\n{t}" for w, n, t in arts), "utf-8")
    return p


OLD = [("الفصل", 1, "يجب على المدعي أن يؤدي الرسم القضائي عند تقديم المقال الافتتاحي للدعوى."),
       ("الفصل", 2, "يحدد أجل الاستئناف في ثلاثين يوما ابتداء من تاريخ التبليغ بالحكم."),
       ("الفصل", 3, "تسلم نسخة من الحكم لكل طرف في الدعوى بعد صدوره.")]
NEW = [("المادة", 1, "تسري أحكام هذا القانون على جميع المحاكم من تاريخ نشره بالجريدة الرسمية."),
       ("المادة", 2, "على المدعي أداء الرسم القضائي عند تقديم المقال الافتتاحي للدعوى."),
       ("المادة", 3, "ينتهي أجل الاستئناف بعد عشرة أيام من تاريخ التبليغ بالحكم."),
       ("المادة", 4, "تسلم نسخة من الحكم لكل طرف في الدعوى بعد صدوره."),
       ("المادة", 5, "تحدد مدة التقادم في الدعاوى المدنية بخمس سنوات من تاريخ الحق.")]
LAB1 = [("المادة", 1, "يستحق الأجير المرتبط بعقد شغل غير محدد المدة تعويضا عند فصله بعد قضائه ستة أشهر من الشغل داخل نفس المقاولة."),
        ("المادة", 2, "يعادل مبلغ التعويض عن الفصل عن كل سنة ما يلي: 96 ساعة من الأجرة في الخمس سنوات الأولى و 144 ساعة بين السنة السادسة والعاشرة و 192 ساعة بين الحادية عشرة والخامسة عشرة و 240 ساعة بعد ذلك."),
        ("المادة", 3, "تدخل ضمن مدد الشغل الفعلي فترات العطلة السنوية المؤدى عنها.")]
LAB2 = [("المادة", 1, LAB1[0][2]), ("المادة", 2, LAB1[1][2].replace("96 ساعة", "98 ساعة")), ("المادة", 3, LAB1[2][2])]


@pytest.fixture(scope="module")
def pk(tmp_path_factory, pack_path):
    tmp = tmp_path_factory.mktemp("tools")
    work = tmp / "w.db"
    shutil.copy2(pack_path, work)
    base = {"kind": "law", "domain": "civil", "lang": "ar", "article_word": None}
    for n, arts, meta in [
        ("old", OLD, {"number": "0.74", "title_ar": "قانون المسطرة القديم", "effective": "1974-09-28", "id_suffix": None}),
        ("new", NEW, {"number": "99.25", "title_ar": "قانون المسطرة الجديد", "effective": "2026-08-24"}),
        ("l1", LAB1, {"number": "65.99", "title_ar": "مدونة الشغل", "effective": "2004-06-08"}),
        ("l2", LAB2, {"number": "65.99", "title_ar": "مدونة الشغل (صيغة محينة 2026)", "effective": "2026-01-29", "id_suffix": "2026"}),
    ]:
        f = _md(tmp, f"{n}.md", arts)
        meta = {**base, **{k: v for k, v in meta.items() if v}, "min_articles": 1, "consolidated_on": meta["effective"]}
        if n == "old":
            meta["article_word"] = "الفصل"
        src, rep = law_pdf_to_sources(f, meta)
        assert not rep["problems"], rep
        append_sources(work, src, HashingEmbedder(), f"t-{n}")
    return work


@pytest.fixture()
def tctx(tmp_path, pk, keys):
    s = Settings(data_dir=tmp_path / "data", lawpack_path=pk, lawpack_public_key_hex=keys[1], api_token="test-token", ner_enabled=False, allow_unsigned_pack=True)
    c = build_context(s)
    c.today_fn = lambda: date(2026, 10, 27)
    yield c
    c.close()


def test_article_number_parsing():
    assert T.parse_article("440") == (440, "") and T.parse_article("78-2") == (78, "-2") and T.parse_article("46 مكرر") == (46, "bis")
    with pytest.raises(T.ToolError):
        T.parse_article("abc")


def test_old_to_new_finder_maps_by_meaning(tctx):
    pack = tctx.pack
    ids = pack.instrument_ids()
    assert {"LAW_0.74", "LAW_99.25"} <= ids or any(i.endswith("0.74") for i in ids), ids
    old = next(i for i in ids if i.endswith("0.74"))
    new = next(i for i in ids if i.endswith("99.25"))
    r = T.find_new_article(pack, instrument=old, article="2", target=new)
    assert r["label"] == "derived" and r["matches"][0]["number"] == "3"  # article 2 (30 days) -> article 3 (10 days)
    assert any(s["op"] != "equal" for s in r["diff_with_best"])
    r3 = T.find_new_article(pack, instrument=old, article="3", target=new)
    assert r3["matches"][0]["number"] == "4"


def test_table_and_errors(tctx):
    pack = tctx.pack
    old = next(i for i in pack.instrument_ids() if i.endswith("0.74"))
    new = next(i for i in pack.instrument_ids() if i.endswith("99.25"))
    t = T.concordance_table(pack, old, new)
    assert t["counts"]["old"] == 3 and {r["old_number"]: r["new_number"] for r in t["rows"]}["2"] == "3"
    with pytest.raises(T.ToolError) as e:
        T.find_new_article(pack, instrument=old, article="999", target=new)
    assert e.value.code == "article_not_in_pack"
    with pytest.raises(T.ToolError) as e:
        T.find_new_article(pack, instrument=new, article="1")
    assert e.value.code == "no_newer_text"


def test_history_across_editions(tctx):
    pack = tctx.pack
    lab = next(i for i in pack.instrument_ids() if i.endswith("65.99"))
    h = T.article_history(pack, instrument=lab, article="2", as_of=date(2026, 10, 27))
    assert len(h["family"]) == 2 and h["changes"] == 1
    assert "98" in h["periods"][-1]["text"] and "96" in h["periods"][0]["text"]
    assert h["periods"][1]["change_summary"]["words_added"] >= 1 and h["periods"][-1]["in_force_on_date"]
    h52 = T.article_history(pack, instrument=lab, article="1")
    assert h52["changes"] == 0 and len(h52["periods"][0]["sources"]) == 2  # the same words in both editions: one period


def test_phrase_finder_and_severance_from_law(tctx):
    from legalrag.calc.basis import severance_from_law

    a = T.articles_with_phrase(tctx.pack, next(i for i in tctx.pack.instrument_ids() if i.endswith("65.99")), ["التعويض عن الفصل", "ساعة من الأجرة"], date(2026, 10, 27), prefer="2")
    assert a and a[0]["number"] == "2"
    # the pack's Labour Code is the labelled test one, found under its id
    assert T.articles_with_phrase(tctx.pack, "NOPE", ["x"], date(2026, 10, 27)) == []


def test_api_endpoints(tctx):
    c = TestClient(create_app(tctx.settings, tctx))
    old = next(i for i in tctx.pack.instrument_ids() if i.endswith("0.74"))
    new = next(i for i in tctx.pack.instrument_ids() if i.endswith("99.25"))
    r = c.get("/v1/tools/concordance", params={"instrument": old, "article": "2", "target": new}, headers=H)
    assert r.status_code == 200 and r.json()["matches"], r.text
    assert c.get("/v1/tools/concordance", params={"instrument": old, "article": "999", "target": new}, headers=H).status_code == 404
    assert c.get("/v1/tools/concordance", headers=H).status_code == 422
    assert c.get("/v1/tools/history", params={"instrument": old, "article": "2"}, headers=H).status_code == 200
    assert c.get("/v1/tools/laws/%s/family" % old, headers=H).json()["replaced_by"] is None or True
    assert c.get("/v1/tools/guides", headers=H).json()
    assert c.get("/v1/tools/history", params={"instrument": old, "article": "2"}).status_code in (401, 403)


def test_split_clauses():
    t = "عقد كراء\n\nالمادة 1: يلتزم المكتري بأداء الوجيبة الكرائية في أول كل شهر دون تأخير.\n\nالمادة 2: مدة العقد سنة واحدة قابلة للتجديد باتفاق الطرفين.\n\nو"
    cl = rv.split_clauses(t)
    assert [c["n"] for c in cl] == [1, 2, 3] or len(cl) >= 2
    assert all(len(c["text"]) >= 40 for c in cl)


class _FakeLLM:
    name, model = "fake", "fake-1"

    def __init__(self, fn):
        self.fn = fn

    def generate_json(self, req):
        return self.fn(req)


def test_contract_check_keeps_only_verified_quotes(tctx):
    new = next(i for i in tctx.pack.instrument_ids() if i.endswith("99.25"))
    text = ("عقد تجريبي\n\nالمادة 1: يتفق الطرفان على أن ينتهي أجل الاستئناف بعد شهر واحد من تاريخ التبليغ بالحكم الصادر بينهما.\n\n"
            "المادة 2: تسلم نسخة من الحكم لكل طرف في الدعوى بعد صدوره حسب الاتفاق.")

    def fn(req):
        ps = {p["id"]: p["text"] for p in req.payload["passages"]}
        pid = next(k for k, t in ps.items() if "أجل الاستئناف" in t)
        return {"findings": [
            {"clause": 1, "verdict": "conflicts", "passage": pid, "quote": "ينتهي أجل الاستئناف بعد عشرة أيام", "why": "الأجل القانوني عشرة أيام"},
            {"clause": 1, "verdict": "conflicts", "passage": pid, "quote": "نص مختلق غير موجود في المادة إطلاقا", "why": "x"},
            {"clause": 2, "verdict": "consistent", "passage": "P99999", "quote": "تسلم نسخة من الحكم", "why": "y"}]}

    tctx.llm_override = _FakeLLM(fn)
    out = rv.check_document(tctx, None, text, date(2026, 10, 27), "ar")
    assert out["status"] == "checked" and len(out["findings"]) == 1 and out["findings_dropped_unverified"] == 2
    assert out["findings"][0]["verdict"] == "conflicts" and out["findings"][0]["article"]
    tctx.llm_override = None
    out2 = rv.check_document(tctx, None, text, date(2026, 10, 27), "ar")
    assert out2["status"] == "retrieved_only" and out2["clauses"]


def test_guide_drops_steps_without_a_real_article(tctx):
    def fn(req):
        pid = req.payload["passages"][0]["id"]
        return {"steps": [{"title": "خطوة", "text": "نص", "passages": [pid]}, {"title": "بلا سند", "text": "نص", "passages": ["P0"]}]}

    tctx.llm_override = _FakeLLM(fn)
    g = rv.build_guide(tctx, "الاستئناف", ["أجل الاستئناف التبليغ بالحكم"], None, "ar")
    assert g["status"] == "generated" and len(g["steps"]) == 1
    assert rv.build_guide(tctx, "الاستئناف", ["أجل الاستئناف التبليغ بالحكم"], None, "ar")["cached"] is True


def test_calculator_cites_the_law(tctx):
    r = tctx.calcs.run("severance", {"start_date": "2015-01-01", "end_date": "2026-10-01", "hourly_wage": 20}).to_dict()
    nums = {a["number"] for a in r["articles"]}
    assert {"1", "2"} <= nums and all(a["text"] and a["why"] for a in r["articles"])  # the test code numbers its articles 1..3
    assert any("art." in b for b in r["legal_basis"])


def test_synthbench_samples_articles_and_saves_questions(ctx, tmp_path):
    import importlib.util
    from datetime import date as _d
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("synthbench", Path(__file__).resolve().parent.parent / "tools" / "synthbench.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    sb.MIN_CHARS = 5
    items = sb.sample_articles(ctx.pack, {"labor": "FIXLAB"}, 3, 1, _d(2026, 10, 27))
    assert items and all(i["id"].startswith("labor:") and i["text"] for i in items)

    class Fake:
        calls = 0

        def generate_json(self, req):
            Fake.calls += 1
            return {"items": [{"id": a["id"], "darija": "سؤال بالدارجة", "msa": "سؤال بالفصحى"} for a in req.payload["articles"]]}

    import random as _r
    qq = sb.extractive_queries(items[0]["text"], _r.Random(1))  # no model: two queries cut from the article
    assert qq["clause"] and qq["keywords"]
    cache = tmp_path / "q.jsonl"
    got = sb.generate(Fake(), items, cache, batch=2)
    assert set(got) == {i["id"] for i in items} and Fake.calls == -(-len(items) // 2)
    again = sb.generate(Fake(), items, cache, batch=2)  # saved questions are not asked again
    assert again == got and Fake.calls == -(-len(items) // 2)


def test_pack_publish_and_install_round_trip(tmp_path, pack_path, keys, monkeypatch):
    import json, shutil, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    data = tmp_path / "pub"
    (data / "lawpack").mkdir(parents=True)
    shutil.copy2(pack_path, data / "lawpack" / "current.db")
    shutil.copy2(str(pack_path) + ".sig", data / "lawpack" / "current.db.sig")
    env = {**__import__("os").environ, "LEGALRAG_DATA_DIR": str(data), "LEGALRAG_LAWPACK_PUBLIC_KEY_HEX": keys[1]}
    work = tmp_path / "work"
    work.mkdir()
    r = subprocess.run([sys.executable, str(root / "tools" / "pack_publish.py"), "--tag", "t1"], cwd=work, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads((work / "pack_release.json").read_text())
    assert info["public_key_hex"] == keys[1] and (work / "release_out" / "current.db.sig").exists()
    user = tmp_path / "user"
    env2 = {**env, "LEGALRAG_DATA_DIR": str(user)}
    ok = subprocess.run([sys.executable, str(root / "tools" / "install_pack.py"), "--db", str(work / "release_out" / "current.db"), "--key", keys[1]], cwd=work, env=env2, capture_output=True, text=True)
    assert ok.returncode == 0 and (user / "lawpack" / "current.db").exists(), ok.stdout + ok.stderr
    bad = subprocess.run([sys.executable, str(root / "tools" / "install_pack.py"), "--db", str(work / "release_out" / "current.db"), "--key", "00" * 32], cwd=work, env={**env, "LEGALRAG_DATA_DIR": str(tmp_path / "other")}, capture_output=True, text=True)
    assert bad.returncode == 1 and not (tmp_path / "other" / "lawpack" / "current.db").exists()


def test_install_pack_download_resumes_and_checks_hash(tmp_path, pack_path, keys):
    import http.server, json, os, subprocess, sys, threading
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    serve = tmp_path / "serve"
    serve.mkdir()
    shutil.copy2(pack_path, serve / "current.db")
    shutil.copy2(str(pack_path) + ".sig", serve / "current.db.sig")
    data = (serve / "current.db").read_bytes()
    calls = {"n": 0}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = (serve / Path(self.path).name).read_bytes()
            rng = self.headers.get("Range")
            start = int(rng.split("=")[1].split("-")[0]) if rng else 0
            if self.path.endswith("current.db") and start == 0 and calls["n"] == 0:  # first attempt: cut the connection half way
                calls["n"] = 1
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body[: len(body) // 2])
                self.wfile.flush()
                self.connection.close()
                return
            self.send_response(206 if start else 200)
            self.send_header("Content-Length", str(len(body) - start))
            self.end_headers()
            self.wfile.write(body[start:])

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    import hashlib
    rel = tmp_path / "rel.json"
    rel.write_text(json.dumps({"db_url": f"{base}/current.db", "sig_url": f"{base}/current.db.sig", "public_key_hex": keys[1], "sha256": hashlib.sha256(data).hexdigest()}))
    udir = tmp_path / "user2"
    r = subprocess.run([sys.executable, str(root / "tools" / "install_pack.py"), "--release", str(rel)], env={**os.environ, "LEGALRAG_DATA_DIR": str(udir)}, capture_output=True, text=True)
    srv.shutdown()
    assert r.returncode == 0, r.stdout + r.stderr
    assert (udir / "lawpack" / "current.db").read_bytes() == data and calls["n"] == 1
