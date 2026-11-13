"""SYNTHETIC fixture sources for tests and local demos. NOT REAL LAW: every instrument is marked
(FIXTURE) and fictional. Real packs are built from official BO / SGG / Adala files (see loader.py).

The fixtures contain the traps the blueprint cares about: article versions that change on a date,
an old/new code split with a transitional rule, a cross-reference, definition articles, and a calculator rate table."""
from __future__ import annotations

SRC = lambda k: {"key": k, "url": f"https://example.invalid/{k}", "fetched_at": "2026-10-01T00:00:00+00:00", "sha256": "f" * 63 + str(len(k) % 10), "kind": "bo_pdf", "edition": "official", "label": "synthetic fixture"}  # noqa: E731


def fixture_sources() -> dict:
    inst = [
        {"instrument_id": "FIXLAB", "kind": "law", "number": "00.01", "short_code": "FIXLAB", "aliases": ["قانون الشغل التجريبي", "Loi travail fictive"],
         "title_ar": "قانون الشغل التجريبي (نص تجريبي)", "title_fr": "Loi fictive sur le travail (FIXTURE)", "bo_number": "0001", "bo_date": "2000-01-01",
         "effective_date": "2000-01-01", "domain": "labor", "language_availability": {"ar": "official", "fr": "official_translation"}, "official_article_count": 4},
        {"instrument_id": "FIXLAB_AMEND_2025", "kind": "law", "number": "00.02", "title_fr": "Loi fictive modifiant la loi fictive sur le travail (FIXTURE)",
         "bo_number": "0002", "bo_date": "2024-12-01", "effective_date": "2025-01-01", "domain": "labor", "edges": [["amends", "FIXLAB"]]},
        {"instrument_id": "FIXCPC_OLD", "kind": "dahir_law", "number": "0.74", "short_code": "FIXCPCOLD", "aliases": ["ancien code fictif"],
         "title_ar": "قانون المسطرة التجريبي القديم (نص تجريبي)", "title_fr": "Ancien code de procédure fictif (FIXTURE)", "effective_date": "1974-09-28", "domain": "civil_procedure"},
        {"instrument_id": "FIXCPC_NEW", "kind": "law", "number": "99.99", "short_code": "FIXCPC", "aliases": ["قانون المسطرة التجريبي"],
         "title_ar": "قانون المسطرة التجريبي الجديد (نص تجريبي)", "title_fr": "Nouveau code de procédure fictif (FIXTURE)", "bo_number": "9999", "bo_date": "2026-02-23",
         "effective_date": "2026-08-24", "domain": "civil_procedure", "edges": [["replaces", "FIXCPC_OLD"]]},
    ]

    def art(iid, n, versions, **kw):
        return {"instrument_id": iid, "number": str(n), "path": kw.pop("path", "الباب الأول"), "versions": versions, **kw}

    def ver(vf, vt, ar, fr, src="s_fix", **kw):
        return {"valid_from": vf, "valid_to": vt, "source": src, "texts": {"ar": {"text": ar, "edition": "official"}, "fr": {"text": fr, "edition": "official"}}, **kw}

    ar_def = "في مدلول هذا القانون يقصد بالأجير كل شخص يؤدي عملا مقابل أجر لدى مشغل."
    fr_def = "Au sens de la présente loi, le salarié est toute personne qui exécute un travail contre rémunération pour un employeur."
    provisions = [
        art("FIXLAB", 1, [ver("2000-01-01", None, ar_def, fr_def, second_texts={"ar": {"text": ar_def, "edition": "official"}})], is_definition=True),
        art("FIXLAB", 5, [
            ver("2000-01-01", "2025-01-01", "مدة التجربة 3 أشهر قابلة للتجديد مرة واحدة.", "La période d'essai est de 3 mois, renouvelable une fois."),
            ver("2025-01-01", None, "مدة التجربة 4 أشهر قابلة للتجديد مرة واحدة.", "La période d'essai est de 4 mois, renouvelable une fois.", amended_by="FIXLAB_AMEND_2025"),
        ]),
        art("FIXLAB", 10, [ver("2000-01-01", None,
            "لا يجوز للمشغل طرد الأجير دون سبب مشروع. ويجب إشعار الأجير كتابة قبل 30 يوما من الطرد، مع مراعاة مقتضيات الفصل 5 من هذا القانون.",
            "L'employeur ne peut licencier le salarié sans motif légitime. Le salarié est informé par écrit 30 jours avant le licenciement, sous réserve de l'article 5 de la présente loi.")]),
        art("FIXLAB", 12, [ver("2000-01-01", None, "الإضراب حق مضمون. يجب إشعار المشغل قبل 10 أيام من تاريخ الإضراب.",
            "La grève est un droit garanti. L'employeur est averti 10 jours avant la date de la grève.")]),
        art("FIXCPC_OLD", 30, [ver("1974-09-28", "2026-08-24", "يمكن استئناف الأحكام داخل أجل 30 يوما من تاريخ التبليغ.",
            "L'appel des jugements peut être interjeté dans un délai de 30 jours à compter de la notification.", path="القسم الثاني")]),
        art("FIXCPC_NEW", 30, [ver("2026-08-24", None, "يمكن استئناف الأحكام داخل أجل 15 يوما من تاريخ التبليغ.",
            "L'appel des jugements peut être interjeté dans un délai de 15 jours à compter de la notification.", path="القسم الثاني")]),
        art("FIXCPC_NEW", 900, [ver("2026-08-24", None, "تطبق المقتضيات السابقة على الأحكام الصادرة قبل تاريخ دخول هذا القانون حيز التنفيذ.",
            "Les dispositions antérieures s'appliquent aux jugements rendus avant l'entrée en vigueur de la présente loi.", path="أحكام انتقالية")], is_transitional=True),
    ]
    return {
        "sources": [SRC("s_fix")],
        "instruments": inst,
        "provisions": provisions,
        "transitional_rules": [
            {"instrument_id": "FIXCPC_NEW", "applies_when": "judgment_before", "cutoff_date": "2026-08-24", "source_provision_id": "FIXCPC_NEW_ART_900",
             "note": "Les jugements rendus avant le 2026-08-24 restent soumis aux dispositions antérieures (règle fictive).", "governs_before": "FIXCPC_OLD", "governs_after": "FIXCPC_NEW"},
        ],
        "deadline_rules": [
            {"kind": "appeal", "case_type": "civil", "regime": "old", "trigger": "notification", "amount": 30, "unit": "days", "valid_from": "1974-09-28", "valid_to": "2026-08-24", "provision_id": "FIXCPC_OLD_ART_30", "note": "fixture"},
            {"kind": "appeal", "case_type": "civil", "regime": "new", "trigger": "notification", "amount": 15, "unit": "days", "valid_from": "2026-08-24", "provision_id": "FIXCPC_NEW_ART_30", "note": "fixture"},
            {"kind": "limitation", "case_type": "fixture_claim", "trigger": "start", "amount": 5, "unit": "years", "provision_id": "FIXLAB_ART_1", "note": "fixture"},
        ],
        "rates": [
            {"key": "FIX_VAT_PCT", "value": 20.0, "unit": "percent", "valid_from": "2024-01-01", "valid_to": "2026-01-01", "note": "fixture rate"},
            {"key": "FIX_VAT_PCT", "value": 18.0, "unit": "percent", "valid_from": "2026-01-01", "note": "fixture rate"},
            {"key": "FIX_IR", "value": None, "unit": "MAD", "valid_from": "2025-01-01", "valid_to": "2026-01-01", "extra": {"brackets": [[0, 30000, 0.0], [30000, 50000, 0.10], [50000, None, 0.20]]}, "note": "fixture brackets"},
            {"key": "SEVERANCE_HOURS_Y1_5", "value": 96, "unit": "hours/year", "valid_from": "2004-06-08", "note": "Law 65-99 art. 53 (verify against the BO)"},
            {"key": "SEVERANCE_HOURS_Y6_10", "value": 144, "unit": "hours/year", "valid_from": "2004-06-08", "note": "Law 65-99 art. 53 (verify against the BO)"},
            {"key": "SEVERANCE_HOURS_Y11_15", "value": 192, "unit": "hours/year", "valid_from": "2004-06-08", "note": "Law 65-99 art. 53 (verify against the BO)"},
            {"key": "SEVERANCE_HOURS_Y16_PLUS", "value": 240, "unit": "hours/year", "valid_from": "2004-06-08", "note": "Law 65-99 art. 53 (verify against the BO)"},
            {"key": "SEVERANCE_MIN_MONTHS", "value": 6, "unit": "months", "valid_from": "2004-06-08", "note": "Law 65-99 art. 53 (verify against the BO)"},
            {"key": "SMALL_CLAIM_LIMIT", "value": 10000, "unit": "MAD", "valid_from": "2026-08-24", "note": "claims up to this amount are decided at first and last instance (blueprint, Law 58.25)"},
        ],
        "decisions": [
            {"decision_id": "FIX_DEC_1", "court": "محكمة النقض (تجريبي)", "decision_date": "2026-01-15", "number": "1/2026", "chamber": "الغرفة الاجتماعية",
             "full_text": "قرار تجريبي يتعلق بمدة التجربة وفق الفصل 5.", "provisions": ["FIXLAB_ART_5"]},
        ],
        "concordance": [{"old": "FIXCPC_OLD_ART_30", "new": "FIXCPC_NEW_ART_30", "note": "appeal deadline article (fixture)"}],
        "last_bo_check": "2026-10-01",
    }
