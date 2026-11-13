"""A chat is a conversation: "and article 215?", "explain it simply", "what about the penalty?" only make sense with the earlier turns.

The frontend sends the earlier turns (pseudonymised here, like the question).  They are used for three things only:
  1. a stand-alone version of the question for understanding and retrieval (written by the model when there is one, by simple rules otherwise);
  2. the law the previous answer was about, so "article 215" without a law means the same law;
  3. a short `conversation` block in the generation request, so the answer can say "as explained above".
They are never a legal source: every claim must still quote a passage found for this question."""
from __future__ import annotations

import re
from typing import Any

from ..llm import prompts
from ..llm.providers import GenRequest
from ..text import stopwords
from ..text.arabic import tokens
from ..text.citations import parse_citations

MAX_TURNS = 40         # turns kept for context (the memory already trimmed them to a budget)
MAX_TURN_CHARS = 900   # per turn sent to the model
MODEL_TURNS = 10       # turns (plus the summary of older ones) sent to the model in a request
FOLLOWUP = re.compile(
    r"^\W*(و|ف|ثم|لكن|وماذا|وما|ماذا عن|وكيف|وهل|وإذا|طيب|اذن|إذن|والمادة|والفصل|"
    r"and|what about|how about|and what|but|so|then|also|et |et si|mais|alors|donc|et les|et la|et le)\b"
    r"|\b(it|this|that|these|those|the same|above|previous|next|ذلك|هذا|هذه|هذا الفصل|هذه المادة|السابق|السابقة|التالي|التالية|المذكور|المذكورة|"
    r"cela|ceci|celui|celle|ci-dessus|précédent|precedent|suivant|simplif|explain|explique|expliqu|وضح|اشرح|بسط|لخص|summari[sz]e|résume|resume|more|plus de|المزيد|أكثر|اكثر)\b",
    re.I)
_PROV_ART = re.compile(r"^(?P<iid>.+?)_ART_\d+")


def clean_history(history: list[Any]) -> list[dict[str, Any]]:
    out = []
    for h in history[-MAX_TURNS:]:
        d = h if isinstance(h, dict) else h.model_dump()
        txt = re.sub(r"\s+", " ", d.get("text") or "").strip()
        if txt:
            out.append({"role": d["role"], "text": txt[:MAX_TURN_CHARS], "cited": list(d.get("cited") or [])})
    return out


def last_user_question(history: list[dict]) -> str | None:
    return next((h["text"] for h in reversed(history) if h["role"] == "user"), None)


def context_instrument(history: list[dict]) -> str | None:
    """The law the most recent answer rested on, when it was ONE law."""
    for h in reversed(history):
        if h["role"] == "assistant" and h.get("cited"):
            ids = {m.group("iid") for c in h["cited"] if (m := _PROV_ART.match(c))}
            return next(iter(ids)) if len(ids) == 1 else None
    return None


def is_followup(text: str, history: list[dict], has_refs_with_law: bool = False) -> bool:
    if not history:
        return False
    from .understand import SMALLTALK
    if SMALLTALK.match(text.strip()):
        return False
    content = [t for t in tokens(text) if t not in stopwords.ALL and len(t) > 1]
    return bool(FOLLOWUP.search(text.strip())) or (len(content) <= 4 and not has_refs_with_law)


def anaphoric(text: str) -> bool:
    return bool(FOLLOWUP.search(text.strip()))


def refs_from_cited(history: list[dict], limit: int = 3):
    """"explain it simply": the articles the previous answer rested on, as exact references."""
    from ..text.citations import CitationRef
    for h in reversed(history):
        if h["role"] == "assistant" and h.get("cited"):
            out = []
            for c in h["cited"][:limit]:
                m = re.match(r"^(?P<iid>.+?)_ART_(?P<n>\d+)(?:_(?P<suf>[A-Z]+))?$", c)
                if m:
                    out.append(CitationRef(m.group("iid"), int(m.group("n")), (m.group("suf") or "").lower(), c, 0, 0))
            return out
    return []


def rule_standalone(text: str, history: list[dict]) -> str:
    """No model: put the previous question next to this one, so retrieval sees the topic.  Same language in practice."""
    prev = last_user_question(history)
    return f"{text} ({prev})" if prev and prev not in text else text


def focus(history: list[dict]) -> list[dict]:
    """What the model sees: the summary of older turns (if any) + the last MODEL_TURNS turns."""
    head = [h for h in history[:1] if h["text"].startswith("[Earlier in this chat]")]
    rest = history[len(head):]
    return head + rest[-MODEL_TURNS:]


def conversation_block(history: list[dict]) -> list[dict[str, str]]:
    return [{"role": h["role"], "text": h["text"]} for h in focus(history)]


def make_summarizer(llm, case_id: str | None, scan: bool = True):
    """(previous summary, older turns) -> new summary, through the same gateway (privacy scan included); None if there is no model."""
    if llm is None:
        return None

    def run(prev: str, turns: list[dict[str, str]]) -> str | None:
        out = llm.generate_json(GenRequest(
            prompts.SUMMARY_SYSTEM, {"previous_summary": prev, "older_messages": [{"role": t["role"], "text": t["text"][:700]} for t in turns]}, prompts.SUMMARY_SCHEMA,
            ([prev] + [t["text"][:700] for t in turns]) if scan else [], case_id, kind="summary"))
        s = (out or {}).get("summary")
        return s.strip() if isinstance(s, str) and len(s.strip()) >= 10 else None

    return run


def rewrite(llm, text: str, history: list[dict], case_id: str | None, scan: bool = True) -> str | None:
    """One small call.  The history is already pseudonymised; the gateway scans it again before anything leaves."""
    try:
        out = llm.generate_json(GenRequest(
            prompts.REWRITE_SYSTEM, {"conversation": conversation_block(history), "last_message": text}, prompts.REWRITE_SCHEMA,
            [text, *[h["text"] for h in focus(history)]] if scan else [], case_id, kind="rewrite"))
    except Exception:  # noqa: BLE001 - the rules are the floor; a provider error never breaks the question
        return None
    s = (out or {}).get("standalone")
    if not isinstance(s, str):
        return None
    s = s.strip()
    return s if 3 <= len(s) <= 800 else None


def law_from_history(text: str, pack, history: list[dict]) -> str | None:
    """An explicit law in the text wins; otherwise the law of the previous answer."""
    refs = parse_citations(text, pack.aliases(), pack.instrument_ids())
    if any(r.instrument_id for r in refs):
        return None
    return context_instrument(history)
