"""Plan the search: split a long, many-sided question (typically a real-life story) into the separate legal issues it contains.

A story such as "my relative's husband locked her in, gives no money, and there is a 16-year-old daughter" holds several legal questions
(her maintenance, the child's maintenance, unlawful confinement / violence, divorce options).  One search for the whole story finds only
the most obvious one, so the model proposes one SHORT sub-question per issue and each is searched on its own.  The model only decides what to
search for: it never answers, and every quote of the final answer is still checked by code.  Without a model nothing changes."""
from __future__ import annotations

from typing import Any

from ..llm.providers import GenRequest
from ..text.arabic import tokens

MIN_TOKENS = 22  # shorter questions are one issue: the normal search is enough

PLAN_SYSTEM = """You prepare the search of a Moroccan legal assistant. The user describes a situation. List the separate LEGAL ISSUES it contains, so that each can be
searched on its own in the Moroccan law texts. Return JSON: {"issues": ["<sub-question>", ...]}.
- At most the number given in "limit". One issue = one legal question (a right to claim, a remedy, a duty of a person, a criminal offence, a procedure, a child's right).
- Cover every side the facts raise, including protection and criminal aspects when the facts suggest them (e.g. confinement, violence, neglect), not only the most obvious claim.
- Always keep these four kinds of issue when the facts touch them, each as its own sub-question (merge others first if there is no room): (1) the spouse's own maintenance / rights,
  (2) the children's maintenance and custody, worded like the law ("نفقة الأولاد ومدتها"، "نفقة البنت"), (3) violence, confinement or neglect and the protection / criminal side,
  (4) the way out for the spouse: divorce for harm, or the complaint to the prosecutor ("التطليق للضرر"، "الشكاية إلى النيابة العامة").
- Write each as a SHORT sub-question in Arabic using the words the law itself uses (e.g. "نفقة الزوجة"، "نفقة الأولاد"، "الحضانة"، "التطليق للضرر"،
  "الطرد من بيت الزوجية"، "إهمال الأسرة"، "العنف ضد المرأة"، "تدابير الحماية"), e.g. "ما حكم منع الزوجة من مغادرة بيت الزوجية؟", "من تجب عليه نفقة البنت القاصر؟".
  Not as a story. No names or dates from the story; a child's age may be kept when it matters (minor / adult).
- Do not answer. Do not name a law or article number unless the user named it. Do not repeat the same issue twice."""

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {"type": "string"}, "maxItems": 6}},
    "required": ["issues"],
}


def worth_planning(text: str) -> bool:
    return len(tokens(text)) >= MIN_TOKENS


def issues(llm, text: str, case_id: str | None, *, limit: int, scan: bool = True) -> list[str]:
    """-> up to `limit` short sub-questions, [] when the model is not available, fails, or finds a single issue."""
    if llm is None or not worth_planning(text):
        return []
    try:
        out = llm.generate_json(GenRequest(PLAN_SYSTEM, {"question": text, "limit": limit}, PLAN_SCHEMA, [text] if scan else [], case_id, kind="plan"))
    except Exception:  # noqa: BLE001 - a provider error never breaks the question: the normal search is used
        return []
    seen: set[str] = set()
    res: list[str] = []
    for q in (out or {}).get("issues") or []:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if 6 <= len(q) <= 220 and q not in seen:
            seen.add(q)
            res.append(q)
    return res[:limit] if len(res) > 1 else []
