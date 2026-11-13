H = {"Authorization": "Bearer test-token"}


def test_health_public_and_token_required(client):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/status").status_code == 401
    assert client.get("/v1/status", headers=H).status_code == 200


def test_pack_and_law_endpoints(client):
    assert client.get("/v1/pack", headers=H).json()
    assert client.get("/v1/instruments", headers=H).status_code == 200
    r = client.get("/v1/provisions/FIXLAB_ART_5", headers=H, params={"as_of": "2024-06-01"})
    assert r.status_code == 200
    assert client.get("/v1/calculators", headers=H).status_code == 200


def test_query_prepare_and_cancel(client):
    r = client.post("/v1/queries", headers=H, json={"question": "M. Ahmed Benali : période d'essai ?", "as_of": "2026-01-01"})
    assert r.status_code == 201 and "Ahmed" not in r.json()["pseudonymised_text"]
    qid = r.json()["query_id"]
    assert client.post(f"/v1/queries/{qid}/cancel", headers=H).json()["status"] == "cancelled"
    assert client.post(f"/v1/queries/{qid}/run", headers=H, json={}).status_code == 404


def test_calculator_endpoint(client):
    r = client.post("/v1/calculators/run", headers=H, json={"tool": "minimum_wage", "inputs": {"date": "2026-02-01"}})
    assert r.status_code == 422


def test_eval_runs(client):
    r = client.post("/v1/eval/run", headers=H)
    assert r.status_code == 200 and "all_gates_pass" in r.json()


def test_rates_and_deadline_rules_listing(client):
    rates = client.get("/v1/rates", headers=H).json()
    keys = {r["key"]: r for r in rates}
    assert "SMIG_HOURLY" in keys and keys["FIX_IR"]["kind"] == "progressive"
    rules = client.get("/v1/deadline-rules", headers=H).json()
    assert rules and {"kind", "case_type", "amount", "unit"} <= set(rules[0])


def test_salary_projection_endpoint(client):
    r = client.post("/v1/calculators/run", headers=H, json={"tool": "salary_projection", "inputs": {"monthly_pay": 3500}})
    assert r.status_code == 200 and len(r.json()["result"]["years"]) == 6


def test_pairing_gives_token_only_to_local_origins(client):
    ok = client.post("/pair", headers={"Origin": "http://localhost:3000", "X-LegalRAG-Pair": "1"})
    assert ok.status_code == 200 and ok.json()["token"]
    assert client.post("/pair", headers={"Origin": "https://evil.example", "X-LegalRAG-Pair": "1"}).status_code == 403
    assert client.post("/pair", headers={"X-LegalRAG-Pair": "1"}).status_code == 403  # no Origin: not a browser app
    assert client.post("/pair", headers={"Origin": "http://localhost:3000"}).status_code == 403  # missing marker header


def test_greeting_and_one_word_queries_are_not_answered_from_a_random_passage(client):
    """"hi" matched a passage containing "HI-TECH" and got a made-up legal answer: greetings get an invitation, nothing is retrieved."""
    for q in ("hi", "Bonjour", "سلام", "merci"):
        r = client.post("/v1/queries", headers=H, json={"question": q, "as_of": "2026-01-01", "auto_run": True})
        assert r.status_code == 201, r.text
        qid = r.json()["query_id"]
        a = client.post(f"/v1/queries/{qid}/run", headers=H, json={}).json()
        assert a["status"] == "needs_clarification" and a["clarification_kind"] == "greeting", a
        assert not a.get("sources") and not a.get("claims")


def test_lexical_reranker_does_not_trust_one_matching_word():
    from legalrag.retrieval.rerankers import LexicalReranker

    s = LexicalReranker().score("hi", ["HI-TECH SEEDS MAROC est autorisée à commercialiser des semences", "autre texte"])
    assert max(s) < 0.30
    assert LexicalReranker().score("période d'essai du contrat", ["la période d'essai du contrat ne peut excéder trois mois"])[0] > 0.5


def _ask(client, question, history=None):
    r = client.post("/v1/queries", headers=H, json={"question": question, "as_of": "2026-01-01", "history": history or [], "auto_run": False})
    assert r.status_code == 201, r.text
    return client.post(f"/v1/queries/{r.json()['query_id']}/run", headers=H, json={}).json()


def test_follow_up_uses_the_law_of_the_previous_answer(client):
    first = _ask(client, "article 5 du FIXLAB")
    cited = [s["provision_id"] for s in first.get("sources", [])][:1]
    assert cited, first
    # "and article 6?" has no law of its own: before, it asked "which law?"; with the chat it continues on the same law
    alone = _ask(client, "et l'article 6 ?")
    assert alone.get("clarification_kind") == "law_unclear"
    follow = _ask(client, "et l'article 6 ?", [
        {"role": "user", "text": "article 5 du FIXLAB"},
        {"role": "assistant", "text": "Réponse sur l'article 5.", "cited": cited},
    ])
    assert follow.get("clarification_kind") != "law_unclear"


def test_history_is_pseudonymised_and_does_not_break_greetings(client):
    r = client.post("/v1/queries", headers=H, json={"question": "et ensuite ?", "history": [{"role": "user", "text": "M. Ahmed Benali : période d'essai ?"}]})
    assert r.status_code == 201
    hi = _ask(client, "hi", [{"role": "user", "text": "article 5 du FIXLAB"}])
    assert hi.get("clarification_kind") == "greeting"


def test_conversation_helpers():
    from legalrag.pipeline import conversation as c
    h = c.clean_history([{"role": "user", "text": "ماذا ينص الفصل 214 من القانون 10.23؟"}, {"role": "assistant", "text": "…", "cited": ["LAW_10.23_ART_214"]}])
    assert c.context_instrument(h) == "LAW_10.23"
    assert [(r.instrument_id, r.number) for r in c.refs_from_cited(h)] == [("LAW_10.23", 214)]
    assert c.is_followup("وماذا عن الفصل 215؟", h) and c.is_followup("explain it simply", h)
    assert not c.is_followup("hi", h) and not c.is_followup("ما هو أجل استئناف حكم مدني في القضايا العادية؟", h)
    assert c.rule_standalone("et la suite ?", h).startswith("et la suite ?")


def test_question_naming_a_law_by_number_searches_inside_that_law(client):
    from legalrag.text.citations import laws_named
    ids = {"DECREE_2.25.966", "DECREE_2.25.966_BO7500", "DECREE_2.25.96", "LAW_10.23"}
    assert laws_named("ما هي فئات الأوراق البنكية التي وافق المرسوم 2.25.966 على سحبها من التداول؟", ids) == ["DECREE_2.25.966", "DECREE_2.25.966_BO7500"]
    assert laws_named("quel est le délai prévu par la loi 10.23 ?", ids) == ["LAW_10.23"]
    assert laws_named("ما هي فئات الأوراق البنكية؟", ids) == []
    from datetime import date
    pack = client.app.state.ctx.pack if hasattr(client.app.state, "ctx") else None
    if pack is not None:
        iid = pack.provision("FIXLAB_ART_5")["instrument_id"] if hasattr(pack, "provision") else next(iter(pack.instrument_ids()))
        assert pack.instrument_chunk_ids([iid], date(2026, 1, 1))


def test_a_named_law_is_searched_first_and_not_dropped_for_a_low_word_overlap(client):
    from datetime import date
    from legalrag.retrieval.engine import RetrievalRequest
    ctx = client.app.state.ctx if hasattr(client.app.state, "ctx") else None
    if ctx is None or ctx.pack is None:
        return
    pack = ctx.pack
    iid = pack.provision("FIXLAB_ART_5")["instrument_id"]
    words = next(iter(pack.chunks(pack.instrument_chunk_ids([iid], date(2026, 1, 1))[:1]).values())).body.split()
    req = dict(query=f"ما الذي ينص عليه {max(words, key=len)} ؟ ومتى يبدأ العمل به؟", as_of=date(2026, 1, 1), lang="ar")
    plain = ctx.engine.retrieve(RetrievalRequest(**req))
    named = ctx.engine.retrieve(RetrievalRequest(**req, focus_instruments=[iid]))
    assert named.candidates and named.candidates[0].chunk.instrument_id == iid
    assert named.coverage.top_score >= plain.coverage.top_score


def test_diagnose_reports_what_the_search_sees(client):
    from legalrag.diagnose import diagnose
    ctx = client.app.state.ctx if hasattr(client.app.state, "ctx") else None
    if ctx is None or ctx.pack is None:
        return
    d = diagnose(ctx, "article 5 du FIXLAB")
    assert {"understood", "coverage", "candidates", "named_law_passages"} <= set(d)


def test_a_name_in_an_earlier_answer_does_not_block_the_next_question(client):
    """Earlier turns were masked AFTER the question: a name found there was recorded as private while the question still had it in clear,
    and the outbound check refused to send ("residual identifiers detected (VAULT_VALUE)")."""
    hist = [{"role": "user", "text": "من عين مندوبا للحكومة لدى القرض الفلاحي؟"},
            {"role": "assistant", "text": "يعين السيد خالد سبيع، مفتش المالية، مندوبا للحكومة لدى القرض الفلاحي للمغرب."}]
    r = client.post("/v1/queries", headers=H, json={"question": "وهل خالد سبيع هو نفسه مندوب الحكومة لدى بنك المغرب؟", "history": hist})
    assert r.status_code == 201
    text = r.json()["pseudonymised_text"]
    assert "سبيع" not in text  # masked in the question too, with the same placeholder as in the history


def _ask_no_date(client, q):
    r = client.post("/v1/queries", headers=H, json={"question": q})
    assert r.status_code == 201, r.text
    return client.post(f"/v1/queries/{r.json()['query_id']}/run", headers=H, json={}).json()


def test_a_year_in_the_question_is_its_subject_not_a_reason_to_ask_for_a_date(client):
    """"نسبة العجز سنة 2024" was answered "the law changed during that period, what is the exact date?": the check looked at EVERY
    article of the pack (something always changes in a year).  Now: a year = the subject (law in force today), and a month is only
    questioned when an article FOUND for the question changed during it."""
    a = _ask_no_date(client, "Quel est le délai d'appel d'un jugement civil en 2024 ?")
    assert a.get("clarification_kind") != "exact_day", a
    assert a["as_of_source"] == "text_year"
    b = _ask_no_date(client, "Quel est le délai d'appel d'un jugement civil notifié en août 2026 ?")  # the appeal article changed on 2026-08-24
    assert b.get("clarification_kind") == "exact_day", b
    c = _ask_no_date(client, "Quel est le délai d'appel d'un jugement civil notifié en septembre 2026 ?")
    assert c.get("clarification_kind") != "exact_day", c


def test_switching_masking_off_really_sends_the_text_as_written(client):
    r = client.post("/v1/queries", headers=H, json={"question": "M. Ahmed Benali : période d'essai ?", "mask": False})
    assert r.status_code == 201
    j = r.json()
    assert "Ahmed Benali" in j["pseudonymised_text"]
    on = client.post("/v1/queries", headers=H, json={"question": "M. Ahmed Benali : période d'essai ?"}).json()
    assert "Ahmed" not in on["pseudonymised_text"]  # default stays masked
    a = client.post(f"/v1/queries/{j['query_id']}/run", headers=H, json={}).json()
    assert a["status"] not in ("review_required",) and not a.get("blocked_kinds"), a
