import shutil
from datetime import date

import pytest

from legalrag.builder.build import build_pack
from legalrag.builder.fixtures import fixture_sources
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.retrieval.engine import RetrievalRequest
from legalrag.services import status as st
from legalrag.store.signing import generate_keypair, verify_pack
from legalrag.text.arabic import normalize, quote_in
from legalrag.text.citations import parse_citations

D = date.fromisoformat


def test_arabic_normalisation():
    assert normalize("الفُصْل ٢٣٠") == normalize("الفصل 230")
    assert quote_in("مدة التجربة", "مُدَّةُ  التجربة 4 أشهر")


def test_citation_parsing(ctx):
    refs = parse_citations("الفصل 5 من FIXLAB وفق article 30 FIXCPC", ctx.pack.aliases())
    assert [(r.instrument_id, r.number) for r in refs] == [("FIXLAB", 5), ("FIXCPC_NEW", 30)]


def test_version_at_is_date_exact_and_valid_to_exclusive(ctx):
    p = ctx.pack
    assert p.version_at("FIXLAB_ART_5", D("2024-12-31"))["valid_from"] == "2000-01-01"
    assert p.version_at("FIXLAB_ART_5", D("2025-01-01"))["valid_from"] == "2025-01-01"  # boundary belongs to the new version
    assert p.version_at("FIXCPC_NEW_ART_30", D("2026-08-23")) is None
    assert p.version_at("FIXCPC_OLD_ART_30", D("2026-08-23")) is not None
    assert p.version_at("FIXCPC_OLD_ART_30", D("2026-08-24")) is None


def test_trust_levels(ctx):
    stats = ctx.pack.trust_stats()["current_versions"]
    assert stats.get("verified") == 1 and stats.get("single_source", 0) >= 4


def test_signature_verification_and_tamper_detection(pack_path, keys, tmp_path):
    assert verify_pack(pack_path, keys[1]).ok
    bad = tmp_path / "t.db"
    shutil.copy(pack_path, bad)
    shutil.copy(str(pack_path) + ".sig", str(bad) + ".sig")
    with open(bad, "r+b") as f:
        f.seek(5000)
        f.write(b"\x00\x01")
    assert verify_pack(bad, keys[1]).state == "invalid"
    assert verify_pack(pack_path, generate_keypair()[1]).state == "invalid"  # wrong publisher key


def test_builder_rejects_overlapping_versions(tmp_path):
    src = fixture_sources()
    art5 = next(p for p in src["provisions"] if p["number"] == "5")
    art5["versions"][0]["valid_to"] = "2025-03-01"  # overlaps the 2025-01-01 version
    res = build_pack(src, tmp_path / "x.db", [HashingEmbedder()], "x")
    assert not res.stats["built"] and any(e["code"] == "overlapping_versions" for e in res.report.errors)


def test_builder_flags_broken_arabic_and_disputes(tmp_path):
    src = fixture_sources()
    art12 = next(p for p in src["provisions"] if p["number"] == "12")
    art12["versions"][0]["texts"]["ar"]["text"] = "ﻻ ﻳﺠﻮﺯ ﻫﺬﺍ ﺍﻟﻨﺺ ﻣﺸﻮﻩ ﺑﺎﻟﻜﺎﻣﻞ"
    res = build_pack(src, tmp_path / "x.db", [HashingEmbedder()], "x")
    assert any(e["code"] == "broken_arabic_order" for e in res.report.errors)
    src = fixture_sources()
    art12 = next(p for p in src["provisions"] if p["number"] == "12")
    art12["versions"][0]["texts"]["fr"]["text"] = art12["versions"][0]["texts"]["fr"]["text"].replace("10", "15")  # AR/FR numbers disagree
    res = build_pack(src, tmp_path / "y.db", [HashingEmbedder()], "y")
    assert res.stats["built"] and res.stats["trust"].get("disputed") == 1


def test_disputed_text_is_never_retrieved(tmp_path):
    src = fixture_sources()
    art12 = next(p for p in src["provisions"] if p["number"] == "12")
    art12["versions"][0]["texts"]["fr"]["text"] = art12["versions"][0]["texts"]["fr"]["text"].replace("10", "15")
    out = tmp_path / "d.db"
    build_pack(src, out, [HashingEmbedder()], "d")
    from legalrag.store.lawpack import LawPack

    p = LawPack(out)
    assert p.version_at("FIXLAB_ART_12", D("2026-01-01")) is None
    assert p.keyword_search('"اضراب" OR "greve"', D("2026-01-01"), 5) == []


def test_unofficial_translation_is_not_a_second_source(tmp_path):
    from legalrag.builder.checks import decide_status

    v = {"controlling_lang": "ar", "texts": {"ar": {"text": "abc"}}, "second_texts": {"ar": {"text": "abc", "edition": "unofficial_translation"}}}
    assert decide_status(v)[0] == "single_source"


def _req(ctx, q, as_of, **kw):
    return RetrievalRequest(query=q, as_of=as_of, today=D("2026-10-27"), lang=kw.pop("lang", "fr"), **kw)


def test_retrieval_selects_version_by_as_of_date(ctx):
    q = "période d'essai combien de mois"
    old = ctx.engine.retrieve(_req(ctx, q, D("2024-06-01"), expand=False))
    new = ctx.engine.retrieve(_req(ctx, q, D("2025-06-01"), expand=False))
    pick = lambda r: next(c for c in r.candidates if c.chunk.provision_id == "FIXLAB_ART_5").chunk.valid_from  # noqa: E731
    assert pick(old) == "2000-01-01" and pick(new) == "2025-01-01"


def test_old_and_new_codes_coexist_around_the_transition(ctx):
    q = "délai d'appel notification jugement"
    before = ctx.engine.retrieve(_req(ctx, q, D("2026-08-23"), expand=False))
    after = ctx.engine.retrieve(_req(ctx, q, D("2026-08-24"), expand=False))
    assert any(c.chunk.provision_id == "FIXCPC_OLD_ART_30" for c in before.candidates)
    assert not any(c.chunk.provision_id == "FIXCPC_NEW_ART_30" for c in before.candidates)
    assert any(c.chunk.provision_id == "FIXCPC_NEW_ART_30" for c in after.candidates)
    assert not any(c.chunk.provision_id == "FIXCPC_OLD_ART_30" for c in after.candidates)


def test_exact_reference_needs_no_search(ctx):
    from legalrag.text.citations import parse_citations

    refs = parse_citations("que dit l'article 12 FIXLAB ?", ctx.pack.aliases())
    r = ctx.engine.retrieve(_req(ctx, "zzz", D("2026-01-01"), exact_refs=refs, expand=False))
    assert r.candidates[0].source == "exact" and r.candidates[0].chunk.provision_id == "FIXLAB_ART_12" and r.coverage.covered


def test_exact_reference_with_no_version_on_date_is_reported(ctx):
    refs = parse_citations("article 30 FIXCPC", ctx.pack.aliases())
    r = ctx.engine.retrieve(_req(ctx, "zzz", D("2026-01-01"), exact_refs=refs, expand=False))
    assert r.unresolved_refs and r.unresolved_refs[0]["reason"] == "no_trusted_version_on_date"


def test_graph_expansion_follows_refers_to(ctx):
    r = ctx.engine.retrieve(_req(ctx, "licenciement sans motif légitime préavis écrit", D("2026-01-01")))
    assert any(c.chunk.provision_id == "FIXLAB_ART_10" for c in r.candidates)
    assert any(c.source == "graph" and c.chunk.provision_id == "FIXLAB_ART_5" for c in r.candidates)
    assert any(c.source == "definition" for c in r.candidates)


def test_transitional_article_added_when_effective_date_between_facts_and_today(ctx):
    r = ctx.engine.retrieve(_req(ctx, "délai d'appel notification", D("2026-09-01"), facts_date=D("2026-03-01")))
    assert any(c.source == "transitional" for c in r.candidates) or any(c.chunk.provision_id == "FIXCPC_NEW_ART_900" for c in r.candidates)


def test_both_versions_shown_when_user_declines_date(ctx):
    r = ctx.engine.retrieve(_req(ctx, "période d'essai", D("2026-01-01"), show_both_versions=True, expand=False))
    assert {c.chunk.valid_from for c in r.candidates if c.chunk.provision_id == "FIXLAB_ART_5"} == {"2000-01-01", "2025-01-01"}


def test_no_match_means_no_coverage(ctx):
    r = ctx.engine.retrieve(_req(ctx, "zxqv blorptastic quibble", D("2026-01-01")))
    assert not r.coverage.covered and r.coverage.reason


def test_embedder_mismatch_falls_back_to_keyword(ctx):
    class Other(HashingEmbedder):
        pass

    ctx.embedder_override = Other("some-other-model")
    r = ctx.engine.retrieve(_req(ctx, "période d'essai", D("2026-01-01"), expand=False))
    assert any("does not match" in n for n in r.notes) and r.candidates


def test_dense_failure_falls_back_to_keyword(ctx):
    class Broken:
        embedder_id, dim, location = "hash-ngram-v1", 512, "cloud"

        def embed(self, texts, case_id=None):
            raise ConnectionError("down")

    ctx.embedder_override = Broken()
    r = ctx.engine.retrieve(_req(ctx, "période d'essai", D("2026-01-01"), expand=False))
    assert any("unreachable" in n for n in r.notes) and r.candidates


def test_status_card_and_history(ctx):
    card = st.status_card(ctx.pack, "MA_LAW_66_23", D("2026-10-27"), D("2026-10-27"))
    assert card["contested"] and card["implementation"]["status"] == "pending" and any("contested" in w.lower() for w in card["warnings"])
    assert st.status_card(ctx.pack, "FIXCPC_NEW", D("2026-08-23"), D("2026-10-27"))["state"] == "NOT_YET_IN_FORCE"
    assert st.status_card(ctx.pack, "FIXCPC_NEW", D("2026-08-24"), D("2026-10-27"))["state"] == "IN_FORCE"
    assert st.status_card(ctx.pack, "FIXCPC_OLD", D("2026-08-24"), D("2026-10-27"))["state"] == "REPEALED"
    assert st.status_card(ctx.pack, "FIXLAB_AMEND_2025", D("2026-01-01"), D("2026-10-27"))["relations"]["amends"] == ["FIXLAB"]


def test_compare_dates_diff(ctx):
    r = st.compare_dates(ctx.pack, "FIXLAB_ART_5", D("2024-01-01"), D("2025-06-01"), "fr")
    ops = {(s["op"], s["text"]) for s in r["diff"]}
    assert ("delete", "3") in ops and ("insert", "4") in ops and not r["same_version"]


def test_pack_change_notes(ctx, tmp_path, keys):
    src = fixture_sources()
    next(p for p in src["provisions"] if p["number"] == "12")["versions"][0]["texts"]["ar"]["text"] += " وتطبق هذه المقتضيات على الجميع."
    out = tmp_path / "new.db"
    build_pack(src, out, [HashingEmbedder()], "fixture-2", keys[0])
    from legalrag.store.lawpack import LawPack

    ch = st.pack_changes(LawPack(out), ctx.pack)
    assert [c["provision_id"] for c in ch["changes"]] == ["FIXLAB_ART_12"] and ch["changes"][0]["change"] == "text_changed"


def test_law_named_by_kind_and_number():
    from legalrag.text.citations import parse_citations
    ids = {"LAW_10.23", "DECREE_2.24.865", "ORG_106.13", "ORDER_666.25"}
    cases = {
        "ماذا ينص الفصل 214 من القانون 10.23؟": ("LAW_10.23", 214),
        "المادة 63 من القانون التنظيمي رقم 106.13": ("ORG_106.13", 63),
        "article 3 du décret n° 2.24.865": ("DECREE_2.24.865", 3),
        "art. 3 de l'arrêté n° 666.25": ("ORDER_666.25", 3),
        "article 214 de la loi 10.23": ("LAW_10.23", 214),
    }
    for text, (iid, n) in cases.items():
        r = parse_citations(text, {}, ids)
        assert [(x.instrument_id, x.number) for x in r] == [(iid, n)], text
    assert parse_citations("الفصل 5 من القانون 99.99", {}, ids)[0].instrument_id is None


def test_article_part_cuts_a_multi_article_chunk():
    from legalrag.store.lawpack import article_part
    b = "قررا ما يلي :\nالمادة الأولى\nنص أول يحيل إلى\nالمادة 2 منه\nمتابعة\nالمادة 2\nنص ثان\nالمادة 3\nنص ثالث"
    assert article_part(b, 1).endswith("متابعة") and "نص ثان" not in article_part(b, 1)
    assert article_part(b, 2) == "المادة 2\nنص ثان"
    assert article_part(b, "3") == "المادة 3\nنص ثالث"
    assert article_part(b, 9) == b  # not in the chunk: unchanged
    assert article_part("المادة 5\nنص وحيد", 5) == "المادة 5\nنص وحيد"


def test_lexical_reranker_arabic_question_words_and_clitics():
    """"متى / أي / وإلى" are question words (normalised stopwords), "استبدالها" is "استبدال": a two-part question reaches the threshold."""
    from legalrag.retrieval.rerankers import LexicalReranker, _terms

    q = "ابتداءً من أي تاريخ تفقد الأوراق البنكية المسحوبة قوتها الإبرائية، وإلى متى يمكن استبدالها؟"
    t = _terms(q)
    assert not {"متي", "اي", "والي", "يمكن"} & set(t) and "استبدال" in t
    a1 = "يوافق على سحب الأوراق البنكية التالية والتي ينتهي تداولها القانوني وتفقد قوتها الإبرائية ابتداء من فاتح يناير 2026"
    a2 = "يستمر استبدال الأوراق البنكية المسحوبة بعد التاريخ المذكور إلى غاية 31 ديسمبر 2030."
    s = LexicalReranker().score(q, [a1, a2, "تتمم أحكام الكمبيالة المسحوبة على مؤسسة بنكية"])
    assert min(s[0], s[1]) > 0.30 and s[2] < 0.2


def test_law_and_code_pass_keeps_laws_in_the_pool(ctx):
    """A second search limited to laws and codes: the kind filter works for keyword and vector search, and retrieval still answers."""
    from legalrag.retrieval.engine import PRIMARY_KINDS

    p = ctx.pack
    one = p.instrument("FIXLAB")["kind"]
    hits = p.keyword_search("الشغل OR التجربة OR الفصل OR العقد", D("2026-10-27"), 20, (one,))
    for cid, _ in hits:
        assert p.chunks([cid])[cid].instrument_kind == one
    emb = ctx.engine._embedder_getter()
    mask = p.kind_mask(emb.embedder_id, (one,))
    idx = p.vector_index(emb.embedder_id)
    assert mask.shape == idx.ids.shape and mask.any()
    got = idx.search(emb.embed(["مدة التجربة"], None)[0], D("2026-10-27"), 5, allow=mask)
    assert got and all(p.chunks([c])[c].instrument_kind == one for c, _ in got)
    for pool in (0, 12):  # the extra pass may be switched off; both ways the engine answers
        ctx.engine.s.primary_pool = pool
        r = ctx.engine.retrieve(RetrievalRequest(query="مدة التجربة في عقد الشغل", as_of=D("2026-10-27"), today=D("2026-10-27")))
        assert r.candidates
    assert PRIMARY_KINDS


def test_broad_pool_needs_a_flat_reranker_and_agreement_of_both_searches():
    from types import SimpleNamespace as NS
    from legalrag.config import Settings
    from legalrag.retrieval.engine import Candidate, Coverage, RetrievalEngine, RetrievalRequest
    from datetime import date

    eng = RetrievalEngine.__new__(RetrievalEngine)
    eng.s = Settings()
    eng._domain_match = lambda ch, doms: True
    mk = lambda i, d, b, sc: Candidate(NS(chunk_id=i), "search", d, b, rrf=1.0 - i / 100, score=sc)
    req = RetrievalRequest(query="q", as_of=date(2026, 1, 1), domains=["family"])
    flat = [mk(i, 5 + i, 10 + i, 0.001) for i in range(10)]
    assert len(eng._broad_pool(req, flat, Coverage())) == eng.s.broad_keep if len(flat) > eng.s.broad_keep else len(flat)
    assert eng._broad_pool(req, [mk(i, None, 10 + i, 0.001) for i in range(10)], Coverage()) == []  # one search only: no agreement
    assert eng._broad_pool(req, [mk(i, 5 + i, 10 + i, 0.5) for i in range(10)], Coverage()) == []  # the reranker is confident: normal path
    assert eng._broad_pool(RetrievalRequest(query="q", as_of=date(2026, 1, 1)), flat, Coverage()) == []  # no known domain
