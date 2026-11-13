from legalrag.privacy.ner import NerDetector


def fake_factory(_model):
    # mimics transformers' aggregation_strategy="simple" with sloppy boundaries (cuts inside the words)
    def pipe(chunk):
        out = []
        i = chunk.find("أحمد")
        if i >= 0:
            out.append({"entity_group": "PII", "score": 0.9, "start": i + 1, "end": i + 6})
        j = chunk.find("0501234567")
        if j >= 0:
            out.append({"entity_group": "CONTACT", "score": 0.95, "start": j, "end": j + 10})
        k = chunk.find("لا")
        if k >= 0:
            out.append({"entity_group": "PII", "score": 0.2, "start": k, "end": k + 2})
        return out
    return pipe


TEXT = "يعمل أحمد محمد في الرياض ورقم هاتفه 0501234567"


def test_spans_snap_to_whole_words_and_map_kinds():
    d = NerDetector(pipeline_factory=fake_factory)
    spans = d.detect(TEXT)
    kinds = {s.kind: TEXT[s.start:s.end] for s in spans}
    assert kinds["PERSON"] == "أحمد محمد"  # partial span grown to whole words
    assert kinds["PHONE"] == "0501234567"
    assert d.status["state"] == "ready"


def test_low_score_and_unlisted_kinds_ignored():
    d = NerDetector(pipeline_factory=fake_factory, kinds=("CONTACT",))
    assert [s.kind for s in d.detect(TEXT)] == ["PHONE"]


def test_non_arabic_text_skipped_and_failure_is_graceful():
    d = NerDetector(pipeline_factory=fake_factory)
    assert d.detect("Monsieur Dupont habite à Paris") == []

    def boom(_m):
        raise OSError("no network")
    d2 = NerDetector(pipeline_factory=boom)
    assert d2.detect(TEXT) == [] and d2.status["state"] == "unavailable" and "no network" in d2.status["error"]


def test_integrates_with_pseudonymiser(client):
    from legalrag.privacy.pseudonymiser import Pseudonymiser
    ctx = client.app.state.ctx
    p = Pseudonymiser(ctx.db, ner=NerDetector(pipeline_factory=fake_factory))
    case = ctx.db.create_case()
    r = p.pseudonymise(TEXT, case)
    assert "أحمد" not in r.text and "0501234567" not in r.text
    restored, _ = p.restore(r.text, case)
    assert "أحمد" in restored and "0501234567" in restored
