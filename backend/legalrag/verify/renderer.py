"""Turns verified output into what the user sees: law / article / BO references computed from chunk IDs (never written by the
model), side-by-side Arabic and French text, trust levels with source links, notices, referrals; restores names LAST."""
from __future__ import annotations

import re

from datetime import date
from typing import Any

from ..pipeline.understand import REFERRALS, msg
from ..retrieval.engine import Candidate
from ..store.lawpack import LawPack

KIND_LABEL = {
    "en": {"law": "Law", "dahir_law": "Dahir-law", "organic_law": "Organic Law", "code": "Code", "decree": "Decree", "order": "Order", "circular": "Circular",
           "treaty": "Treaty", "constitution": "Constitution", "court_decision": "Decision", "administrative_guidance": "Administrative guidance"},
    "fr": {"law": "Loi", "dahir_law": "Dahir portant loi", "organic_law": "Loi organique", "code": "Code", "decree": "Décret", "order": "Arrêté", "circular": "Circulaire",
           "treaty": "Traité", "constitution": "Constitution", "court_decision": "Décision", "administrative_guidance": "Doctrine administrative"},
    "ar": {"law": "القانون رقم", "dahir_law": "ظهير بمثابة قانون", "organic_law": "القانون التنظيمي رقم", "code": "مدونة", "decree": "المرسوم رقم", "order": "قرار", "circular": "منشور",
           "treaty": "معاهدة", "constitution": "الدستور", "court_decision": "قرار قضائي", "administrative_guidance": "توجيه إداري"},
}
ART_WORD = {"en": "art.", "fr": "art.", "ar": "الفصل/المادة"}
TRUST_NOTE = {
    "verified": "Matches two official sources.",
    "single_source": "One official source, not cross-checked.",
    "derived": "Built by applying amending laws: check the amendment chain shown.",
}
DISCLAIMER = {
    "en": "Information only, not legal advice. Check the date of the law and consult a lawyer before acting.",
    "fr": "Information uniquement, pas un conseil juridique. Vérifiez la date de la loi et consultez un avocat avant d'agir.",
    "ar": "هذه معلومات للاطلاع فقط وليست استشارة قانونية. تأكد من تاريخ سريان النص، واستشر محاميا قبل اتخاذ أي إجراء.",
}
L = lambda lang: {"darija": "ar"}.get(lang, lang if lang in ("ar", "fr", "en") else "en")  # noqa: E731


_CONSOLIDATED = {"ar": "صيغة محينة بتاريخ", "fr": "version consolidée au", "en": "consolidated on"}


def consolidated_on(inst: dict) -> str | None:
    """The date an updated edition (Adala / SGG «صيغة محينة») was brought up to, as the importer recorded it in the instrument's note."""
    m = re.search(r"consolidated on (\d{4}-\d{2}-\d{2})", inst.get("status_note") or "")
    return m.group(1) if m else None


def law_label(inst: dict, lang: str) -> str:
    lang = L(lang)
    if inst.get("short_code") and inst["kind"] in ("code", "dahir_law"):
        base = inst["short_code"]
    else:
        kind = KIND_LABEL[lang].get(inst["kind"], inst["kind"])
        base = f"{kind} {inst.get('number') or ''}".strip()
    c = consolidated_on(inst)
    return f"{base} ({_CONSOLIDATED[lang]} {c})" if c else base


OTHER_TEXT_WORD = {"ar": "ملحق / ديباجة", "fr": "annexe / préambule", "en": "annex / preamble"}


def source_entry(pack: LawPack, cand: Candidate, lang: str, as_of: date, cid: str) -> dict[str, Any]:
    ch = cand.chunk
    view = pack.provision_view(ch.pv_id) or {}
    inst = pack.instrument(ch.instrument_id) or {}
    texts = view.get("texts", {})
    other = next((l for l in ("ar", "fr") if l != ch.lang and l in texts), None)
    trail = []
    if ch.verification_status == "derived":
        trail = [{"valid_from": v["valid_from"], "amended_by": v["amended_by"], "bo_number": v.get("amender_bo")} for v in pack.versions(ch.provision_id) if v["amended_by"]]
    vt = date.fromisoformat(ch.valid_to) if ch.valid_to else None
    own = texts.get(ch.lang) or next(iter(texts.values()), None)
    # paragraph_no 0 = a chunk that is not an article (preamble, annex, table) hanging on the text's first article: show ITS text, not that article
    other_text = ch.paragraph_no == 0
    full = ch.body if other_text else ((own or {}).get("text") or ch.body)  # the WHOLE article as the pack holds it, never the retrieval chunk
    loc = None if other_text else pack.article_location(ch.provision_id, ch.pv_id)
    return {
        "chunk_text": ch.body, "pages": ({"start": loc["page_start"], "end": loc["page_end"]} if loc else None), "has_pdf": bool(loc and loc.get("url")),
        "id": cid, "chunk_id": ch.chunk_id, "provision_id": ch.provision_id, "instrument_id": ch.instrument_id, "role": cand.source, "note": cand.note, "via": cand.via,
        "law": law_label(inst, lang) if inst else ch.instrument_id, "title_ar": inst.get("title_ar"), "title_fr": inst.get("title_fr"),
        "article": (OTHER_TEXT_WORD[L(lang)] if other_text else f"{ART_WORD[L(lang)]} {ch.number}"), "kind": "other_text" if other_text else "article", "path": ch.path, "paragraph_no": ch.paragraph_no,
        "bo": {"number": inst.get("bo_number"), "date": inst.get("bo_date")}, "consolidated_on": consolidated_on(inst),
        "valid_from": ch.valid_from, "valid_to": ch.valid_to,
        "in_force_on_as_of": date.fromisoformat(ch.valid_from) <= as_of and (vt is None or vt > as_of),
        "law_in_force_on": as_of.isoformat(),
        "controlling_lang": ch.controlling_lang, "lang": ch.lang, "text": full,
        "other_language": ({"lang": other, "text": texts[other]["text"], "edition": texts[other]["edition"]} if other else None),
        "trust": ch.verification_status, "trust_note": TRUST_NOTE.get(ch.verification_status, ""), "amendment_chain": trail,
        "source": view.get("source"), "contested": inst.get("status_flag") == "ACTIVE_CONTESTED", "status_note": inst.get("status_note"),
        "relevance": round(cand.score, 4),
    }


def referral_notices(flags: list[str], lang: str) -> list[str]:
    return [msg(REFERRALS, f, lang) for f in flags if f in REFERRALS]


_BRING = {
    "procedure": {
        "en": ["the decision / judgment and its notification date", "the filing date and the court", "any summons or notice received"],
        "fr": ["la décision / le jugement et sa date de notification", "la date d'introduction et le tribunal", "toute convocation ou notification reçue"],
        "ar": ["القرار أو الحكم وتاريخ تبليغه", "تاريخ رفع الدعوى والمحكمة", "أي استدعاء أو إشعار توصلت به"],
    },
    "calculation": {
        "en": ["pay slips or contract with dates and amounts", "the exact start and end dates"],
        "fr": ["les bulletins de paie ou le contrat, avec dates et montants", "les dates exactes de début et de fin"],
        "ar": ["كشوف الأجر أو العقد مع التواريخ والمبالغ", "تاريخا البداية والنهاية بدقة"],
    },
    "other": {
        "en": ["the documents concerned (contract, notice, decision) with their dates", "the exact dates of the facts", "the question you want a professional to answer"],
        "fr": ["les documents concernés (contrat, notification, décision) avec leurs dates", "les dates exactes des faits", "la question que vous voulez poser à un professionnel"],
        "ar": ["الوثائق المعنية (العقد، الإشعار، القرار) مع تواريخها", "التواريخ الدقيقة للوقائع", "السؤال الذي تريد طرحه على مختص"],
    },
}
_REASONS = {
    "no provision valid on the as-of date matched the question": {"fr": "aucun article en vigueur à la date retenue ne correspond à la question", "ar": "لا توجد مادة سارية في التاريخ المعتمد تطابق السؤال"},
    "the best match is not clearly better than the next candidate": {"fr": "le meilleur résultat n'est pas nettement meilleur que le suivant", "ar": "أفضل نتيجة ليست أفضل بوضوح من التي تليها"},
    "too few independent supporting provisions": {"fr": "trop peu d'articles indépendants à l'appui", "ar": "عدد المواد المستقلة الداعمة قليل جدا"},
    "insufficient evidence": {"fr": "preuves insuffisantes", "ar": "الأدلة غير كافية"},
    "model abstained": {"fr": "le modèle s'est abstenu", "ar": "امتنع النموذج عن الجواب"},
    "drafting and strategy are out of scope: this tool quotes the law": {"fr": "la rédaction et la stratégie sont hors périmètre : cet outil cite la loi", "ar": "الصياغة ووضع الاستراتيجية خارج نطاق الأداة: فهي تستشهد بالقانون فقط"},
}


def _reason(reason: str, lang: str) -> str:
    lg = L(lang)
    if lg == "en":
        return reason
    import re

    m = re.match(r"best match score ([\d.]+) is below the threshold ([\d.]+)$", reason)
    if m:
        return (f"أفضل نتيجة بلغت {m[1]} وهي دون الحد المطلوب {m[2]}" if lg == "ar" else f"le meilleur score ({m[1]}) est inférieur au seuil ({m[2]})")
    return _REASONS.get(reason, {}).get(lg, reason)


def abstention(reason: str, as_of: date, lang: str, qtype: str, searched: dict[str, Any], found: list[dict[str, Any]]) -> dict[str, Any]:
    lg = L(lang)
    bring = _BRING.get(qtype, _BRING["other"])[lg]
    reason = _reason(reason, lang)
    return {"reason": reason, "searched": searched, "found": found, "bring_to_professional": bring, "as_of": as_of.isoformat(), "referral": True}
