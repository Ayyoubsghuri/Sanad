"""The articles behind each calculator, found in the law pack itself (in force on the calculation date, any edition of the law).

An article is found by words it must contain, never by a number typed here alone: `prefer` is tried first and kept only when its text has
the words, so a renumbered or consolidated edition still gives the right article.  Nothing found = nothing shown (no invented reference).
Severance hours and the minimum seniority are also READ from the Labour Code articles, so the calculator can be checked against the law
(and still works when the pack has no rate table for them)."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..store.lawpack import LawPack

# tool -> [(law id, words the article must contain, preferred number, what the article is for)]
BASIS: dict[str, list[tuple[str, list[str], str | None, str]]] = {
    "severance": [
        ("LAW_65.99", ["يستحق", "ستة أشهر", "فصله"], "52", "right to severance: indefinite contract, six months in the same business"),
        ("LAW_65.99", ["التعويض عن الفصل", "ساعة من الأجرة"], "53", "amount: hours of pay per year of service, by seniority band"),
        ("LAW_65.99", ["الأجر المعتمد لتقدير التعويض عن الفصل"], None, "which pay is used for the computation"),
        ("LAW_65.99", ["بمثابة أخطاء جسيمة"], "39", "serious misconduct: no notice and no severance"),
    ],
    "minimum_wage": [
        ("LAW_65.99", ["لا يمكن أن يقل الحد الأدنى القانوني للأجر"], "356", "the minimum wage is set by regulation"),
        ("LAW_65.99", ["يحتسب الحد الأدنى القانوني للأجر"], "357", "what counts in the minimum wage"),
    ],
    "wage_arrears": [
        ("LAW_65.99", ["لا يمكن أن يقل الحد الأدنى القانوني للأجر"], "356", "the minimum wage is set by regulation"),
        ("LAW_65.99", ["يحتسب الحد الأدنى القانوني للأجر"], "357", "what counts in the minimum wage"),
        ("LAW_65.99", ["تقادم بمرور سنتين", "الحقوق الناتجة عن عقود الشغل"], "395", "claims from an employment contract expire after two years"),
    ],
    "salary_projection": [
        ("LAW_65.99", ["لا يمكن أن يقل الحد الأدنى القانوني للأجر"], "356", "the minimum wage is set by regulation"),
        ("LAW_65.99", ["علاوة الأقدمية", "بعد قضائه سنتين"], "350", "seniority bonus rates"),
    ],
    "inheritance_shares": [
        ("LAW_70.03", ["الفرض سهم مقدر"], None, "fixed shares are served first"),
        ("LAW_70.03", ["الفروض المقدرة ستة"], None, "the six fixed shares"),
        ("LAW_70.03", ["من الربع إلى الثمن"], None, "a spouse's share is reduced by children"),
        ("LAW_70.03", ["من الثلث إلى السدس"], None, "the mother's share is reduced by children"),
        ("LAW_70.03", ["للذكر مثل حظ الأنثيين"], None, "residue: a son takes twice a daughter's share"),
    ],
}


def _short_law(title: str | None) -> str | None:
    """"القانون المتعلق بمدونة الشغل (صيغة محينة 2026)" -> "مدونة الشغل": the title without the edition note and the "law on" opening."""
    if not title:
        return title
    t = re.sub(r"\s*\(.*?\)\s*", " ", title).strip()
    return re.sub(r"^(?:القانون|الظهير الشريف|ظهير شريف)\s+(?:رقم\s+[\d.]+\s+)?(?:المتعلق|بمثابة)\s+(?:ب)?", "", t).strip() or title


def calc_articles(pack: LawPack, tool: str, on: date, result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from ..services.tools import articles_with_phrase  # here: services import the calculators' package at start-up

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for law, words, prefer, why in BASIS.get(tool, []):
        for a in articles_with_phrase(pack, law, words, on, prefer=prefer, limit=1):
            if a["provision_id"] not in seen:
                seen.add(a["provision_id"])
                out.append({**a, "law_short": _short_law(a.get("law")), "why": why, "found_by": "words in the article (" + " + ".join(words) + ")"})
    # deadline / limitation rows name their article: show its text on the date
    for pid in (result or {}).get("_provisions", []):
        if pid and pid not in seen and pack.provision(pid):
            v = pack.version_at(pid, on)
            if v:
                p = pack.provision(pid) or {}
                t = pack.texts(v["pv_id"])
                out.append({"provision_id": pid, "instrument_id": p.get("instrument_id"), "number": p.get("number"),
                            "text": (t.get("ar") or next(iter(t.values()), {"text": ""}))["text"], "valid_from": v["valid_from"], "valid_to": v["valid_to"],
                            "trust": v["verification_status"], "law": (pack.instrument(p.get("instrument_id") or "") or {}).get("title_ar"),
                            "why": "the rule this result applies", "found_by": "the rule row names this article"})
                seen.add(pid)
    return out


# ------------------------------------------------------------------------------------------------ values read from the articles
_WORD_NUM = {"ستة": 6, "سته": 6, "ثلاثة": 3, "ثلاثه": 3, "اثني عشر": 12, "سنة": 12, "سنه": 12}


def severance_from_law(pack: LawPack, on: date) -> dict[str, Any] | None:
    """{"hours": [96, 144, 192, 240], "min_months": 6, "articles": {...}} read from the Labour Code in force on `on`; None when not found."""
    from ..services.tools import articles_with_phrase

    amt = articles_with_phrase(pack, "LAW_65.99", ["التعويض عن الفصل", "ساعة من الأجرة"], on, prefer="53")
    if not amt:
        return None
    hours = [int(h) for h in re.findall(r"(\d{2,3})\s*ساع", amt[0]["text"])][:4]
    if len(hours) != 4 or hours != sorted(hours):
        return None
    out: dict[str, Any] = {"hours": hours, "min_months": None, "articles": {"amount": amt[0]["number"]}}
    right = articles_with_phrase(pack, "LAW_65.99", ["يستحق", "ستة أشهر", "فصله"], on, prefer="52")
    if right:
        m = re.search(r"بعد\s*قضائه\s*(\S+)\s*أشهر", re.sub(r"\s+", " ", right[0]["text"]))
        if m and m.group(1) in _WORD_NUM:
            out["min_months"] = _WORD_NUM[m.group(1)]
        elif m and m.group(1).isdigit():
            out["min_months"] = int(m.group(1))
        out["articles"]["right"] = right[0]["number"]
    return out
