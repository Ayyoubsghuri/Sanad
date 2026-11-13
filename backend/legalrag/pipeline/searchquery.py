"""The question in Darija / French / English -> the same question in the formal Arabic of Moroccan legislation, used for SEARCH only.

The law pack is in Arabic and both the keyword index and the reranker work far better on the words of the law ("الطلاق", "عقد الشغل", "الحضانة")
than on «كيفاش نقدر نطلب الطلاق», "how do I get a divorce" or «comment divorcer».  The question the user typed is never replaced: it is still
shown, still sent to the answer step (so the answer comes back in the user's language), and still takes part in the search as a sub-question.

One small call per question, remembered for the session.  The text it receives is already pseudonymised and the gateway scans it again.
Nothing is changed when there is no model (offline mode), when the question is already formal Arabic, or when the model's answer does not look
right (not Arabic, a placeholder lost, a number changed): the normal search then runs on the original words."""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from ..llm.providers import GenRequest
from ..privacy.pseudonymiser import find_placeholders
from ..text import arabic

SYSTEM = """You prepare a question about Moroccan law for a search engine whose documents are Moroccan laws written in formal Arabic (فصحى).
Rewrite the user's question as ONE clear question in formal Arabic, using the vocabulary the legislation itself uses (for example: الطلاق، التطليق،
الشقاق، النفقة، الحضانة، عقد الشغل، الفصل التعسفي، التعويض عن الفصل، مدة الشغل، الأجر، الكراء، التقادم، الشيك، الإفلاس، المخالفة، السياقة).
The input may be Moroccan Darija, French, English or already Arabic. Rules: keep every number, date, amount, article number and law number exactly as
written; keep placeholders such as [PERSON_1] unchanged; keep the meaning and the situation; add no fact, no law and no article that the user did not
mention; do NOT answer the question. If the user asks HOW to do something (start a procedure, claim a right), also name in the same sentence the kinds of procedure the legislation distinguishes (for example for a divorce: الطلاق بإذن المحكمة، الطلاق الاتفاقي، التطليق للشقاق، الخلع، التمليك). If the question has several parts, keep them all in one sentence or two. Return JSON {"arabic": "..."}, nothing else."""
SCHEMA: dict[str, Any] = {"type": "object", "properties": {"arabic": {"type": "string"}}, "required": ["arabic"]}

_CACHE: "OrderedDict[str, str | None]" = OrderedDict()
_NUM = re.compile(r"\d+(?:[.,/-]\d+)*")


def needs_rewrite(lang: str, text: str) -> bool:
    """Darija, French, English (or anything not Arabic) is rewritten; formal Arabic already speaks the law's language."""
    if lang == "ar":
        return False
    return len(arabic.tokens(text)) >= 2 or bool(text.strip())


def _valid(src: str, out: str) -> bool:
    if not (3 <= len(out) <= 900) or arabic.arabic_ratio(out) < 0.6:
        return False
    if set(find_placeholders(src)) - set(find_placeholders(out)):  # a masked name must survive
        return False
    return all(n in out or n.replace(",", ".") in out for n in set(_NUM.findall(src)) if len(n) >= 2)  # numbers, dates, law numbers stay


def to_formal_arabic(llm, text: str, lang: str, case_id: str | None = None, scan: bool = True) -> str | None:
    """The formal-Arabic search question, or None (then the original words are searched)."""
    if llm is None or not text or not needs_rewrite(lang, text):
        return None
    key = text.strip()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    try:
        out = (llm.generate_json(GenRequest(SYSTEM, {"question": text, "language": lang}, SCHEMA, [text] if scan else [], case_id, kind="rewrite")) or {}).get("arabic")
    except Exception:  # noqa: BLE001 - the original question is searched; a provider error never breaks the answer
        return None
    res = out.strip() if isinstance(out, str) and _valid(text, out.strip()) else None
    _CACHE[key] = res
    while len(_CACHE) > 500:
        _CACHE.popitem(last=False)
    return res
