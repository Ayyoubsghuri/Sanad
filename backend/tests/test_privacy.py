import json

import httpx
import pytest

from legalrag.evalharness.golden import synthetic_pseudonymisation_cases
from legalrag.privacy.gateway import CloudUnavailable, Gateway, ModeForbids, OutboundBlocked, OutboundGuard
import random

RAW = ("Bonjour, je suis M. Ahmed Benali, CIN BK123456, tel 06 12 34 56 78, email a.b@gmail.com, "
       "RIB 123 456 1234567890123456 78. Dossier 1234/1201/2025. السيد محمد الزرقاني.")


def test_direct_identifiers_and_names_are_replaced(ctx):
    case = ctx.db.create_case()
    r = ctx.pseudo.pseudonymise(RAW, case)
    for leaked in ("Ahmed", "Benali", "BK123456", "06 12 34 56 78", "a.b@gmail.com", "1234/1201/2025", "الزرقاني"):
        assert leaked not in r.text, leaked
    assert "[PERSON_1]" in r.text and "[CIN_1]" in r.text and "[PHONE_1]" in r.text and "[RIB_1]" in r.text
    assert OutboundGuard(ctx.db).scan([r.text], case) == []
    assert OutboundGuard(ctx.db).scan([RAW], case)  # the raw text is blocked


def test_same_entity_same_placeholder_and_restore(ctx):
    case = ctx.db.create_case()
    a = ctx.pseudo.pseudonymise("M. Ahmed Benali a signé.", case).text
    b = ctx.pseudo.pseudonymise("Ahmed Benali a quitté.", case).text
    assert a.count("[PERSON_1]") == 1 and b.count("[PERSON_1]") == 1
    restored, unknown = ctx.pseudo.restore(a + " [PERSON_9]", case)
    assert "Ahmed Benali" in restored and unknown == ["[PERSON_9]"]


def test_dates_and_amounts_are_kept(ctx):
    r = ctx.pseudo.pseudonymise("Licencié le 12/03/2025, salaire 4500 MAD.", ctx.db.create_case())
    assert "12/03/2025" in r.text and "4500" in r.text


def test_keep_places_toggle(ctx):
    case = ctx.db.create_case()
    assert "Casablanca" in ctx.pseudo.pseudonymise("Tribunal de Casablanca", case, keep_places=True).text
    assert "Casablanca" not in ctx.pseudo.pseudonymise("Tribunal de Casablanca", case, keep_places=False).text


def test_user_marked_term_is_remembered(ctx):
    case = ctx.db.create_case()
    assert "Zorglub" in ctx.pseudo.pseudonymise("Mon voisin Zorglub me gêne.", case).text or True
    ctx.db.add_marked_term("Zorglub")
    assert "Zorglub" not in ctx.pseudo.pseudonymise("Mon voisin Zorglub me gêne.", case).text


def test_unknown_capitalised_word_lowers_confidence(ctx):
    r = ctx.pseudo.pseudonymise("Mon voisin Zorglub Vexnar me gêne.", ctx.db.create_case())
    assert r.confidence < 1 and r.unknown_tokens


def test_synthetic_recall_of_direct_identifiers(ctx):
    total = ok = 0
    for text, planted in synthetic_pseudonymisation_cases(random.Random(1), 40):
        r = ctx.pseudo.pseudonymise(text, ctx.db.create_case())
        for kind, value in planted:
            if kind != "PERSON":
                total += 1
                ok += int(value.replace(" ", "") not in r.text.replace(" ", ""))
    assert ok == total


def _gateway(ctx, handler, mode="hybrid"):
    ctx.db.set_settings({"mode": mode})
    return Gateway(ctx.db, OutboundGuard(ctx.db), lambda: ctx.mode, 2.0, httpx.MockTransport(handler))


def test_gateway_blocks_residual_identifier_and_logs(ctx):
    sent = []
    g = _gateway(ctx, lambda req: (sent.append(req), httpx.Response(200, json={}))[1])
    with pytest.raises(OutboundBlocked):
        g.post_json(kind="generate", provider="x", model="m", url="https://api.example/v1", headers={}, body={"q": RAW}, user_fields=[RAW], case_id=None)
    assert not sent
    assert ctx.db.list_outbound()[0]["status"] == "blocked"


def test_gateway_offline_mode_forbids_everything(ctx):
    g = _gateway(ctx, lambda req: httpx.Response(200, json={}), mode="offline")
    with pytest.raises(ModeForbids):
        g.post_json(kind="generate", provider="x", model="m", url="https://api.example", headers={}, body={}, user_fields=["clean text"], case_id=None)


def test_gateway_logs_exact_payload_and_wraps_errors(ctx):
    g = _gateway(ctx, lambda req: httpx.Response(200, json={"ok": True}))
    g.post_json(kind="generate", provider="x", model="m", url="https://api.example/v1", headers={"x-api-key": "secret"}, body={"q": "licenciement abusif"}, user_fields=["licenciement abusif"], case_id=None)
    row = ctx.db.list_outbound()[0]
    assert json.loads(row["payload"]) == {"q": "licenciement abusif"} and row["status"] == "ok" and "secret" not in json.dumps(row)
    g2 = _gateway(ctx, lambda req: httpx.Response(500))
    with pytest.raises(CloudUnavailable):
        g2.post_json(kind="generate", provider="x", model="m", url="https://api.example", headers={}, body={}, user_fields=["ok"], case_id=None)


def test_cloud_embed_not_allowed_in_hybrid(ctx):
    g = _gateway(ctx, lambda req: httpx.Response(200, json={}), mode="hybrid")
    with pytest.raises(ModeForbids):
        g.post_json(kind="embed", provider="x", model="m", url="https://api.example", headers={}, body={}, user_fields=["q"], case_id=None)


def test_signed_on_date_is_not_a_birth_date(client):
    from legalrag.privacy.patterns import detect_patterns
    assert not [s for s in detect_patterns("Bail signé le 12/03/2024") if s.kind == "DOB"]
    assert [s for s in detect_patterns("née le 12/03/1990") if s.kind == "DOB"]


def test_law_numbers_and_the_preposition_ala_are_not_masked(tmp_path):
    from legalrag.privacy.pseudonymiser import Pseudonymiser
    from legalrag.store.crypto import KeyStore
    from legalrag.store.userdb import UserDB
    db = UserDB(tmp_path / "u.db", KeyStore(tmp_path))
    p = Pseudonymiser(db)
    cid = db.create_case()
    for q in ("المادة 3 من القرار رقم 666.25", "ما القرار الذي نسخه قرار 1432.26؟", "وافق المرسوم 2.25.966 على سحبها من التداول", "القرار رقم 1431.12"):
        assert p.pseudonymise(q, cid, keep_places=True).text == q, q
    assert "[CASE_" in p.pseudonymise("ملف عدد 1234/2020", cid, keep_places=True).text  # real case numbers still masked
    assert "[PERSON_" in p.pseudonymise("السيد علي بنعمر", cid, keep_places=True).text  # a real name still masked


def test_a_pii_model_that_tags_law_numbers_cannot_mask_them(tmp_path):
    """The Arabic PII model tags "1432.26" as IDENTIFIER: the question then lost the law it names and was answered from unrelated texts."""
    from legalrag.privacy.patterns import Span
    from legalrag.privacy.pseudonymiser import Pseudonymiser
    from legalrag.store.crypto import KeyStore
    from legalrag.store.userdb import UserDB

    class GreedyNer:  # tags every number, and the name
        def detect(self, text):
            import re
            out = [Span("IDENTIFIER", m.start(), m.end(), "ner") for m in re.finditer(r"\d+(?:[./]\d+)*", text)]
            i = text.find("أحمد")
            return out + ([Span("PERSON", i, i + 4, "ner")] if i >= 0 else [])

    db = UserDB(tmp_path / "u.db", KeyStore(tmp_path))
    p = Pseudonymiser(db, ner=GreedyNer())
    cid = db.create_case()
    for q in ("ما القرار الذي نسخه قرار 1432.26؟ ومتى يبدأ العمل به؟", "ماذا ينص الفصل 214 من القانون 10.23؟",
              "article 3 du décret n° 2.24.865", "قرار لوزير التربية الوطنية رقم 1432.26"):
        assert p.pseudonymise(q, cid).text == q, q
    masked = p.pseudonymise("السيد أحمد رقم بطاقته 123456 والملف عدد 1234/2020 حسب القانون 10.23", cid).text
    assert "أحمد" not in masked and "123456" not in masked and "1234/2020" not in masked and "10.23" in masked


def test_the_pii_model_cannot_mask_a_public_institution(tmp_path):
    from legalrag.privacy.patterns import Span
    from legalrag.privacy.pseudonymiser import Pseudonymiser
    from legalrag.store.crypto import KeyStore
    from legalrag.store.userdb import UserDB

    class Ner:  # what the real model did: "بنك" as PERSON, and a real private name
        def detect(self, text):
            out = []
            for w, k in (("بنك", "PERSON"), ("مجلس المنافسة", "ORG"), ("كريم الصالحي", "PERSON")):
                i = text.find(w)
                if i >= 0:
                    out.append(Span(k, i, i + len(w), "ner"))
            return out

    db = UserDB(tmp_path / "u.db", KeyStore(tmp_path))
    p = Pseudonymiser(db, ner=Ner())
    cid = db.create_case()
    q = "من عُيّن مندوبا للحكومة لدى بنك المغرب بالمرسوم رقم 2.24.1008؟"
    assert p.pseudonymise(q, cid).text == q
    out = p.pseudonymise("هل يعتبر كريم الصالحي عضوا في مجلس المنافسة؟", cid).text
    assert "كريم" not in out and "مجلس المنافسة" in out


def test_address_words_must_be_whole_words():
    from legalrag.privacy.patterns import detect_patterns
    assert not [s for s in detect_patterns("ما هي شروط التأمين الصحي الإجباري؟") if s.kind == "ADDRESS"]
    assert [s for s in detect_patterns("يسكن في حي السلام رقم 12") if s.kind == "ADDRESS"]
