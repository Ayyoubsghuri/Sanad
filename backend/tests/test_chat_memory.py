from legalrag.pipeline import memory as M
from legalrag.pipeline.conversation import focus


def _fill(mem, sid, n, summarizer=None):
    for i in range(n):
        mem.add_turn(sid, f"question {i} " + "س" * 300, f"answer {i} " + "ص" * 600, [f"LAW_1_ART_{i}"], summarizer)


def test_unknown_chat_is_seeded_from_browser_history():
    m = M.ChatMemory()
    ctx = m.context("a", [{"role": "user", "text": "hello", "cited": []}, {"role": "assistant", "text": "hi", "cited": ["LAW_1_ART_1"]}])
    assert [t["role"] for t in ctx] == ["user", "assistant"] and ctx[1]["cited"] == ["LAW_1_ART_1"]


def test_long_chat_is_folded_into_a_summary_and_recent_turns_stay():
    m = M.ChatMemory()
    seen = []

    def summarizer(prev, turns):
        seen.append(len(turns))
        return "summary of " + str(len(turns))

    _fill(m, "s", 40, summarizer)
    ctx = m.context("s")
    assert ctx[0]["text"].startswith(M.SUMMARY_MARK) and seen
    assert ctx[-1]["text"].startswith("answer 39") and ctx[-2]["text"].startswith("question 39")
    assert sum(len(t["text"]) for t in ctx) < M.RECENT_BUDGET_CHARS + M.SUMMARY_MAX + 100
    assert len(focus(ctx)) <= 11  # summary + MODEL_TURNS


def test_without_a_model_the_summary_is_an_extract():
    m = M.ChatMemory()
    _fill(m, "s", 40, None)
    first = m.context("s")[0]["text"]
    assert first.startswith(M.SUMMARY_MARK) and "question " in first and len(first) <= M.SUMMARY_MAX + 60


def test_a_failing_summarizer_never_breaks_the_chat():
    m = M.ChatMemory()

    def boom(prev, turns):
        raise RuntimeError("provider down")

    _fill(m, "s", 40, boom)
    assert m.context("s")
