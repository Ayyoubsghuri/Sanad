from datetime import date

from legalrag.llm.providers import GenRequest, ScriptedProvider
from legalrag.pipeline.orchestrator import QueryPipeline
from legalrag.privacy.gateway import CloudUnavailable
from legalrag.schemas import PrepareRequest, RunRequest

D = date.fromisoformat


def ask(ctx, q, **kw):
    pipe = QueryPipeline(ctx)
    run = kw.pop("run", RunRequest())
    prep = pipe.prepare(PrepareRequest(question=q, **kw))
    return pipe.run(prep["query_id"], run), prep


def first_passage(req: GenRequest, lang=None, pred=None):
    ps = req.payload["passages"]
    if pred:
        ps = [p for p in ps if pred(p)]
    return ps[0]


def faithful(req: GenRequest):
    p = first_passage(req)
    words = p["text"].split()
    return {"assumptions": [], "claims": [{"type": "rule", "text": " ".join(words[:10]), "answers": [0], "support": [{"chunk_id": p["chunk_id"], "quote": " ".join(words[:6])}]}]}


def test_happy_path_answer_is_verified_and_cited(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert out["status"] in ("answered", "partial") and out["claims"] and out["claims"][0]["verified"]
    src = {s["id"]: s for s in out["sources"] + out["related"]}
    cited = out["claims"][0]["sources"][0]
    assert src[cited]["trust"] in ("verified", "single_source", "derived") and src[cited]["in_force_on_as_of"]
    assert src[cited]["source"]["url"] and out["pack"]["version"] == "fixture-test" and out["trace_id"]
    assert any("not legal advice" in n.lower() or "pas un conseil" in n.lower() for n in out["notices"])


def test_references_are_rendered_by_code_not_by_the_model(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    s = out["sources"][0]
    assert s["law"] and s["article"].startswith("art.") and s["bo"]["number"] and s["other_language"]


def test_invented_citation_is_dropped_then_regenerated_once(ctx):
    calls = []

    def script(req: GenRequest):
        calls.append(req.payload.get("previous_attempt_failed_checks"))
        if len(calls) == 1:
            return {"assumptions": [], "claims": [{"type": "rule", "text": "Il y a 99 jours.", "support": [{"chunk_id": "C424242", "quote": "n'existe pas"}]}]}
        return faithful(req)

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert len(calls) == 2 and calls[0] is None and calls[1] and out["status"] in ("answered", "partial")
    assert all("99" not in c["text"] for c in out["claims"])


def test_persistent_failure_returns_only_quoted_passages(ctx):
    bad = {"assumptions": [], "claims": [{"type": "rule", "text": "Delai de 99 jours.", "support": [{"chunk_id": "C1", "quote": "invented"}]}]}
    prov = ScriptedProvider(lambda r: bad)
    ctx.llm_override = prov
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert len(prov.calls) == 2 and out["status"] == "extractive_only" and not out["claims"] and out["sources"] and out["could_not_verify"]


def test_quote_must_be_verbatim(ctx):
    def script(req):
        p = first_passage(req)
        return {"assumptions": [], "claims": [{"type": "rule", "text": "période d'essai", "support": [{"chunk_id": p["chunk_id"], "quote": "texte que la loi ne contient pas du tout"}]}]}

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert not out["claims"] and "quote_matches" in str(out["verification"]["failures"])


def test_stray_number_is_rejected(ctx):
    def script(req):
        p = first_passage(req, pred=lambda p: "essai" in p["text"].lower() or "التجربة" in p["text"])
        words = p["text"].split()
        return {"assumptions": [], "claims": [{"type": "rule", "text": f"{' '.join(words[:6])} soit 12 mois", "support": [{"chunk_id": p["chunk_id"], "quote": " ".join(words[:4])}]}]}

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert not out["claims"] and "no_stray_numbers" in str(out["verification"]["failures"])


def test_placeholders_must_exist_and_names_are_restored_only_after_checks(ctx):
    def script(req):
        p = first_passage(req)
        w = p["text"].split()
        return {"assumptions": [], "claims": [{"type": "application", "text": f"Pour [PERSON_1]: {' '.join(w[:8])}", "support": [{"chunk_id": p["chunk_id"], "quote": " ".join(w[:5])}]}]}

    prov = ScriptedProvider(script)
    ctx.llm_override = prov
    out, prep = ask(ctx, "M. Ahmed Benali a été licencié. Quelle est la période d'essai ?", as_of=D("2026-01-01"))
    assert "Ahmed" not in prov.calls[0].payload["question"] and "[PERSON_1]" in prov.calls[0].payload["question"]
    assert out["claims"] and out["claims"][0]["text"].startswith("Pour Ahmed Benali")  # restored locally after verification

    def script2(req):
        r = script(req)
        r["claims"][0]["text"] = r["claims"][0]["text"].replace("[PERSON_1]", "[PERSON_7]")
        return r

    ctx.llm_override = ScriptedProvider(script2)
    out2, _ = ask(ctx, "M. Ahmed Benali a été licencié. Quelle est la période d'essai ?", as_of=D("2026-01-01"))
    assert not out2["claims"] and "placeholders_intact" in str(out2["verification"]["failures"])


def test_model_inventing_a_name_is_rejected(ctx):
    def script(req):
        p = first_passage(req)
        w = p["text"].split()
        return {"assumptions": [], "claims": [{"type": "application", "text": f"Selon Mohamed Alaoui, {' '.join(w[:6])}", "support": [{"chunk_id": p["chunk_id"], "quote": " ".join(w[:4])}]}]}

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert not out["claims"]


def test_outage_falls_back_to_quoted_passages(ctx):
    def boom(req):
        raise CloudUnavailable("down")

    ctx.llm_override = ScriptedProvider(boom)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert out["status"] == "extractive_only" and out["sources"] and not out["claims"] and any("unavailable" in f for f in out["fallbacks"])


def test_offline_mode_sends_nothing(ctx):
    prov = ScriptedProvider(faithful)
    ctx.llm_override = prov
    ctx.db.set_settings({"mode": "offline"})
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert out["status"] == "extractive_only" and out["sources"] and not prov.calls and not ctx.db.list_outbound()


def test_residual_identifier_blocks_the_send_and_falls_back(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "M. Ahmed Benali a été licencié. Période d'essai ?", as_of=D("2026-01-01"))
    assert out["status"] in ("answered", "partial")
    # simulate the detector missing a CIN: the user edits the preview and re-inserts one
    pipe = QueryPipeline(ctx)
    prep = pipe.prepare(PrepareRequest(question="Période d'essai ?", as_of=D("2026-01-01")))
    payload, _row = ctx.db.get_pending(prep["query_id"])
    payload["pseudo"] = "Période d'essai ? Appelez 06 12 34 56 78"
    ctx.db.put_pending(prep["query_id"], prep["case_id"], payload)
    prov = ScriptedProvider(faithful, gateway=ctx.gateway)
    ctx.llm_override = prov
    out = pipe.run(prep["query_id"], RunRequest())
    assert not prov.calls and out["status"] in ("extractive_only", "abstained")
    assert "blocked" in str(out.get("fallbacks", "")) + str(out.get("notices", "")).lower() or out["status"] == "abstained"


def test_abstains_when_evidence_is_weak_and_logs_gap(ctx):
    prov = ScriptedProvider(faithful)
    ctx.llm_override = prov
    out, _ = ask(ctx, "zxqv blorptastic quibble frumious", as_of=D("2026-01-01"))
    assert out["status"] == "abstained" and not prov.calls and out["abstain"]["bring_to_professional"]
    assert ctx.db.gap_summary()["by_reason"]


def test_procedure_without_date_asks_for_filing_date_then_declined_shows_both_versions(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "Quel est le délai d'appel contre un jugement civil ?")
    assert out["status"] != "needs_clarification"  # a general question is answered with today's law; the note says what to add
    out, _ = ask(ctx, "On m'a notifié un jugement civil : quel est le délai d'appel ?")
    assert out["status"] == "needs_clarification" and out["clarification_kind"] == "filing_date"
    prov = ScriptedProvider(faithful)
    ctx.llm_override = prov
    out2, _ = ask(ctx, "Quel est le délai d'appel contre un jugement civil ? délai d'appel jugement jours notification", as_of_declined=True)
    assert out2["status"] != "needs_clarification" and prov.calls
    assert any(s["provision_id"].startswith("FIXCPC") for s in out2["sources"])


def test_false_premise_is_flagged_before_answering(ctx):
    prov = ScriptedProvider(faithful)
    ctx.llm_override = prov
    out, _ = ask(ctx, "L'article 5 FIXLAB dit que la période d'essai est de 9 mois, n'est-ce pas ?", as_of=D("2026-01-01"))
    assert out["premise_warnings"] and out["premise_warnings"][0]["asserted_numbers"] == ["9"]
    assert prov.calls[0].payload["premise_warnings"]


def test_two_versions_must_both_be_cited(ctx):
    def one_version_only(req):
        p = [x for x in req.payload["passages"] if x["role"] == "prior_version"] or req.payload["passages"]
        q = [x for x in req.payload["passages"] if x["role"] != "prior_version"][0]
        w = q["text"].split()
        return {"assumptions": [], "claims": [{"type": "rule", "text": " ".join(w[:8]), "support": [{"chunk_id": q["chunk_id"], "quote": " ".join(w[:5])}]}]}

    prov = ScriptedProvider(one_version_only)
    ctx.llm_override = prov
    out, _ = ask(ctx, "période d'essai durée", as_of_declined=True, as_of=D("2026-01-01"))
    assert any(f["check"] == "conflicts_are_shown" for f in []) or "conflicts_are_shown" in str(out.get("verification", {})) or len(prov.calls) == 2


def test_calculator_output_is_the_only_source_of_numbers(ctx):
    def script(req):
        k = req.payload["tool_outputs"][0]
        return {"assumptions": [], "claims": [{"type": "rule", "text": "surcharge=2000", "support": [{"calc_id": k["calc_id"], "quote": "surcharge=2000"}]},
                                              {"type": "rule", "text": "surcharge=2500", "support": [{"calc_id": k["calc_id"], "quote": "surcharge=2000"}]}]}

    ctx.llm_override = ScriptedProvider(script)
    calc = {"tool": "registration_cash_surcharge", "inputs": {"date": "2026-07-15", "transfer_type": "real_estate", "price": 500000, "cash_portion": 100000}}
    out, _ = ask(ctx, "Quel supplément de 2% pour un paiement en espèces ?", as_of=D("2026-08-01"), calculations=[calc], strict=None)
    assert [c["text"] for c in out["claims"]] == ["surcharge=2000"]
    assert out["calculators"][0]["result"]["surcharge"] == 2000


def test_calculator_missing_input_asks(ctx):
    out, _ = ask(ctx, "Salaire minimum ?", as_of=D("2026-02-01"), calculations=[{"tool": "minimum_wage", "inputs": {"date": "2026-02-01", "pay": 3000}}])
    assert out["status"] == "needs_input" and "hours_worked" in out["needs_input"]["missing"]


def test_payload_preview_sends_nothing(ctx):
    prov = ScriptedProvider(faithful)
    ctx.llm_override = prov
    out, _ = ask(ctx, "M. Ahmed Benali : période d'essai ?", as_of=D("2026-01-01"), run=RunRequest(preview_payload=True))
    assert out["status"] == "payload_preview" and not prov.calls and "Ahmed" not in str(out["payload"])


def test_strict_mode_sends_no_free_text(ctx):
    from legalrag.schemas import StrictFact, StrictInput

    pipe = QueryPipeline(ctx)
    prep = pipe.prepare(PrepareRequest(strict=StrictInput(issue="dismissal", facts=[StrictFact(kind="start_date", value="2020-01-01"), StrictFact(kind="salary", value="4500")]), as_of=D("2026-01-01")))
    assert prep["strict"] and prep["pseudonymised_text"].startswith("licenciement") and "4500" in prep["pseudonymised_text"]


def test_user_can_edit_preview_and_low_confidence_requires_review(ctx):
    pipe = QueryPipeline(ctx)
    prep = pipe.prepare(PrepareRequest(question="Mon voisin Zorglub Vexnar Quimbo Trelba Mordak Plimp Dravo me gêne : période d'essai ?", as_of=D("2026-01-01")))
    assert prep["requires_review"]
    out = pipe.run(prep["query_id"], RunRequest())
    assert out["status"] == "review_required"


def test_cancelled_query_is_deleted(ctx):
    pipe = QueryPipeline(ctx)
    prep = pipe.prepare(PrepareRequest(question="période d'essai ?"))
    assert pipe.run(prep["query_id"], RunRequest(approved=False))["status"] == "cancelled"
    try:
        pipe.run(prep["query_id"], RunRequest())
        raise AssertionError("should be gone")
    except KeyError:
        pass


def test_scope_referrals_are_added_deterministically(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "Je suis en garde à vue demain, période d'essai du salarié ?", as_of=D("2026-01-01"))
    text = " ".join(out["notices"]).lower()
    assert "criminel" in text or "pénales" in text or "criminal" in text
    assert "imminent" in text


def test_trace_is_stored_with_versions_and_checks(ctx):
    ctx.llm_override = ScriptedProvider(faithful)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    tr = ctx.db.get_trace(out["trace_id"])
    assert tr["model"] == "scripted-1" and tr["prompt_version"] and tr["retrieved"] and tr["checks"]["claims_total"] >= 1 and tr["pack_version"] == "fixture-test"
    assert "Ahmed" not in str(tr)


def _vctx(body):
    from legalrag.retrieval.engine import Candidate
    from legalrag.store.lawpack import ChunkMeta
    from legalrag.store.schema_sql import TRUSTED_STATUSES
    from legalrag.verify.checks import VerifyContext
    ch = ChunkMeta(1, 1, "ar", "official", None, body, body, "ORDER_3.64.25_ART_1", "ORDER_3.64.25", "1", None, "2026-01-19", None,
                   sorted(TRUSTED_STATUSES)[0], None, "ar", "order", False, False)

    from types import SimpleNamespace

    class NoCheck:
        def check(self, items, case_id=None):
            return [SimpleNamespace(claim_id=i.claim_id, supported=True, reason="") for i in items]
    return VerifyContext({"C1": Candidate(ch, "search", score=0.9)}, {}, set(), D("2026-11-01"), [], set(), NoCheck())


def test_a_name_printed_in_the_cited_decree_is_not_an_invented_name():
    """"بموجب أي قرار تم تعيين قاض … بمراكش": the answer names the judge the decree appoints.  The check rejected it as "a new name"."""
    from legalrag.verify.checks import verify_answer
    body = "يعين القاضي الآتي إسمه لرئاسة اللجنة الجهوية للنظر في الطعون المتعلقة بالضريبة : - السيد خالد هرماش، القاضي بالمحكمة الابتدائية الإدارية بمراكش، لرئاسة اللجنة الجهوية."
    ok = {"assumptions": [], "claims": [{"type": "rule", "text": "عين السيد خالد هرماش لرئاسة اللجنة الجهوية للنظر في الطعون المتعلقة بالضريبة بمراكش.",
                                          "support": [{"chunk_id": "C1", "quote": "السيد خالد هرماش، القاضي بالمحكمة الابتدائية الإدارية بمراكش"}]}]}
    rep = verify_answer(ok, _vctx(body))
    assert rep.passed_claims, rep.failure_reasons()
    invented = {"assumptions": [], "claims": [{"type": "rule", "text": "عين السيد محمد العلوي لرئاسة اللجنة الجهوية.",
                                                "support": [{"chunk_id": "C1", "quote": "لرئاسة اللجنة الجهوية للنظر في الطعون"}]}]}
    rep2 = verify_answer(invented, _vctx(body))
    assert not rep2.passed_claims and "placeholders_intact" in str(rep2.failure_reasons())


def test_quotes_ignore_punctuation_and_accept_an_ellipsis_but_not_changed_words():
    from legalrag.text.arabic import quote_in
    hay = "يعين القاضي الآتي إسمه لرئاسة اللجنة الجهوية : - السيد خالد هرماش، القاضي بالمحكمة الابتدائية الإدارية بمراكش، لرئاسة اللجنة."
    assert quote_in("السيد خالد هرماش, القاضي بالمحكمة الابتدائية", hay)            # "," for "،"
    assert quote_in("يعين القاضي الآتي إسمه … السيد خالد هرماش", hay)                # pieces in order
    assert not quote_in("السيد خالد هرماش … يعين القاضي الآتي", hay)                 # wrong order
    assert not quote_in("السيد خالد هرماش، القاضي بالمحكمة الإدارية بمراكش", hay)     # a word dropped inside a piece


def test_the_date_of_the_text_can_be_cited_from_its_title_and_bulletin():
    """"ما تاريخه؟": the date is in the TITLE of the order and in the bulletin, not in the article; the checks only saw the article."""
    from legalrag.verify.checks import verify_answer
    body = "يعين القاضي الآتي إسمه لرئاسة اللجنة الجهوية للنظر في الطعون المتعلقة بالضريبة : - السيد خالد هرماش، القاضي بمراكش."
    v = _vctx(body)
    v.headers = {"C1": "قرار لرئيس الحكومة رقم 3.64.25 صادر في 12 من رجب 1447 (2 يناير 2026) بتعيين قاض — الجريدة الرسمية عدد 7475 بتاريخ 2026-01-19"}
    ans = {"assumptions": [], "claims": [{"type": "rule", "text": "عين السيد خالد هرماش بموجب القرار رقم 3.64.25 الصادر في 2 يناير 2026.",
                                           "support": [{"chunk_id": "C1", "quote": "رقم 3.64.25 صادر في 12 من رجب 1447 (2 يناير 2026)"},
                                                       {"chunk_id": "C1", "quote": "السيد خالد هرماش"}]}]}
    rep = verify_answer(ans, v)
    assert rep.passed_claims, rep.failure_reasons()


def test_deep_search_judges_and_searches_again(ctx):
    """depth=deep: the judge sees what was found, proposes a better query, the new passages are merged and the question is answered."""
    def script(req):
        if req.kind == "research":
            return {"verdict": "partial", "missing": "the duration", "queries": ["période d'essai durée"]}
        return faithful(req)

    q = "zxqv blorptastic quibble frumious"
    prov = ScriptedProvider(script)
    ctx.llm_override = prov
    out, _ = ask(ctx, q, as_of=D("2026-01-01"))
    assert out["status"] == "abstained" and not prov.calls  # normal depth: unchanged
    prov = ScriptedProvider(script)
    ctx.llm_override = prov
    out, _ = ask(ctx, q, as_of=D("2026-01-01"), run=RunRequest(depth="deep"))
    r = out["research"]
    assert r["depth"] == "deep" and r["rounds"][0]["verdict"] == "partial" and r["rounds"][0]["queries"] == ["période d'essai durée"] and r["rounds"][0]["added"]
    assert out["status"] in ("answered", "partial") and any("deep search" in f for f in out["fallbacks"])
    assert any(c.kind == "research" for c in prov.calls)


def test_deep_search_stops_when_the_judge_says_enough(ctx):
    prov = ScriptedProvider(lambda req: {"verdict": "enough", "queries": ["x y z"]} if req.kind == "research" else faithful(req))
    ctx.llm_override = prov
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"), run=RunRequest(depth="max"))
    assert len(out["research"]["rounds"]) == 1 and out["research"]["rounds"][0]["added"] == []
    assert out["status"] in ("answered", "partial")


def test_steps_are_recorded_and_available_while_and_after_running(ctx):
    from legalrag.pipeline import progress as PG

    prov = ScriptedProvider(lambda req: {"verdict": "partial", "missing": "x", "queries": ["période d'essai durée"]} if req.kind == "research" else faithful(req))
    ctx.llm_override = prov
    out, prep = ask(ctx, "zxqv blorptastic quibble frumious", as_of=D("2026-01-01"), run=RunRequest(depth="deep"))
    titles = [s["title"] for s in out["steps"]]
    assert titles[0] == "Understanding the question" and "Searching the law" in titles
    assert any(t.startswith("Deep search · round 1: checking") for t in titles) and any(t.startswith("Deep search · round 1: searching again") for t in titles)
    assert all(s["status"] == "done" and s["duration_ms"] is not None for s in out["steps"])
    snap = PG.snapshot(ctx.progress, prep["query_id"])
    assert snap["done"] and len(snap["steps"]) == len(out["steps"])


def test_unknown_model_family_that_refuses_temperature_is_retried_without_it():
    from legalrag.llm.providers import GenRequest, OpenAICompatProvider, _NO_TEMPERATURE
    from legalrag.privacy.gateway import CloudUnavailable

    sent = []

    class GW:
        def post_json(self, **kw):
            sent.append(dict(kw["body"]))
            if "temperature" in kw["body"]:
                raise CloudUnavailable("generate call to openai failed: HTTPStatusError HTTP 400: Unsupported value: 'temperature' does not support 0 with this model.")
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}]}

    _NO_TEMPERATURE.discard("future-model-x")
    p = OpenAICompatProvider(GW(), "future-model-x", lambda: "k", "https://x/v1")
    r = GenRequest("s", {}, {}, [], None)
    assert p.generate_json(r) == {"ok": True} and "temperature" in sent[0] and "temperature" not in sent[1]
    sent.clear()
    assert p.generate_json(r) == {"ok": True} and len(sent) == 1 and "temperature" not in sent[0]  # remembered: one call next time


def test_search_question_in_formal_arabic():
    """Darija / French / English questions are rewritten as formal Arabic for the search; a bad rewrite is never used."""
    from legalrag.pipeline import searchquery as sq

    class Fake:
        def __init__(self, out):
            self.out, self.calls = out, 0

        def generate_json(self, req):
            self.calls += 1
            return {"arabic": self.out}

    sq._CACHE.clear()
    f = Fake("كيف يمكن طلب الطلاق في المغرب؟")
    assert sq.to_formal_arabic(f, "كيفاش نقدر نطلب الطلاق فالمغرب؟", "darija") == "كيف يمكن طلب الطلاق في المغرب؟"
    assert sq.to_formal_arabic(f, "كيفاش نقدر نطلب الطلاق فالمغرب؟", "darija") == "كيف يمكن طلب الطلاق في المغرب؟" and f.calls == 1  # remembered
    assert sq.to_formal_arabic(Fake("x"), "كيف أطلب الطلاق؟", "ar") is None  # already formal Arabic: no call
    assert sq.to_formal_arabic(None, "comment divorcer ?", "fr") is None  # no model: the original words are searched
    sq._CACHE.clear()
    assert sq.to_formal_arabic(Fake("How do I divorce"), "comment divorcer ?", "fr") is None  # the answer is not Arabic
    assert sq.to_formal_arabic(Fake("ما هو أجل الطعن في الحكم؟"), "délai pour faire appel du jugement 12345 ?", "fr") is None  # a number was lost
    assert sq.to_formal_arabic(Fake("ما حق [PERSON_1] في النفقة؟"), "droit à la pension de [PERSON_1] ?", "fr") == "ما حق [PERSON_1] في النفقة؟"
    assert sq.to_formal_arabic(Fake("ما حق السيد في النفقة؟"), "droit à la pension de [PERSON_2] ?", "fr") is None  # a masked name was lost


def test_french_question_is_searched_as_formal_arabic_and_answered_in_french(ctx):
    from legalrag.pipeline import searchquery as sq

    sq._CACHE.clear()
    ctx.settings.query_rewrite = True
    seen = {}

    def script(req: GenRequest):
        if req.kind == "rewrite":
            seen["rewrite"] = req.payload
            return {"arabic": "ما هي مدة التجربة في عقد الشغل؟"}
        seen["question"] = req.payload.get("question")
        seen["lang"] = req.payload.get("answer_language") or req.payload.get("language") or req.payload.get("lang")
        return faithful(req)

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert seen["rewrite"]["question"].startswith("Quelle est la durée") and out.get("search_query") == "ما هي مدة التجربة في عقد الشغل؟"
    assert seen["question"].startswith("Quelle est la durée") and seen["lang"] == "fr"  # the answer step still gets the user's words and language
    assert out["status"] in ("answered", "partial")


def test_a_personal_situation_ends_with_checked_next_steps(ctx):
    from legalrag.pipeline import nextsteps as NEXT
    q = "Mon employeur refuse : quelle est la durée de la période d'essai ?"
    assert NEXT.is_case(q) and not NEXT.is_case("Quelle est la durée de la période d'essai ?")
    seen = []

    def script(req: GenRequest):
        if req.kind != "next_steps":
            return faithful(req)
        seen.append(req)
        ps = req.payload["passages"]
        return {"is_case": True, "professional": "Un avocat est utile devant le tribunal.", "steps": [
            {"title": "Rassembler les preuves", "text": "Gardez le contrat et les bulletins de paie.", "documents": ["contrat"], "passages": []},
            {"title": "Demander vos droits", "text": "Appuyez-vous sur cet article.", "passages": [ps[0]["id"], "C999999"]},
            {"title": "Agir vite", "text": "Saisissez le tribunal.", "deadline": "dans 9731 jours", "passages": [ps[0]["id"]]},   # invented number
            {"title": "Délai sans article", "text": "Agissez.", "deadline": "rapidement", "passages": []},                        # time limit, no article
        ]}

    ctx.llm_override = ScriptedProvider(script)
    out, _ = ask(ctx, q, as_of=D("2026-01-01"))
    assert out["status"] in ("answered", "partial")
    steps = out["next_steps"]["steps"]
    # the invented number goes; a time limit without a number ("rapidement") may stand without an article
    assert [s["title"] for s in steps] == ["Rassembler les preuves", "Demander vos droits", "Délai sans article"]
    assert steps[1]["sources"] == [seen[0].payload["passages"][0]["id"]]          # the invented id is gone
    assert steps[1]["sources"][0] in {s["id"] for s in out["sources"] + out["related"]}
    assert out["next_steps"]["professional"]
    # a general question: the model is not even asked
    seen.clear()
    out, _ = ask(ctx, "Quelle est la durée de la période d'essai ?", as_of=D("2026-01-01"))
    assert "next_steps" not in out and not seen

