import json

from legalrag.builder import checks
from legalrag.builder.from_bo import bo_to_sources, freeze_pdfs, parse_article_number

BO_MD = """---
<!-- page 1 -->

## نصوص عامة

## ظهير شريف رقم 1.25.67 صادر في 5 جمادى الأولى 1447 (27 أكتوبر 2025) بتغيير وتتميم الظهير الشريف رقم 1.03.194 الصادر في 14 رجب 1424 المتعلق بمدونة الشغل.

نحن محمد السادس. يرسم ما يلي:

المادة الأولى

تغير وتتمم أحكام المادة 5 من الظهير الشريف المشار إليه أعلاه على النحو التالي: مدة التجربة أربعة أشهر قابلة للتجديد مرة واحدة.

المادة 2

يدخل هذا الظهير الشريف حيز التنفيذ ابتداء من تاريخ نشره بالجريدة الرسمية.

المادة الحادية عشرة

تطبق مقتضيات هذا الظهير الشريف على جميع عقود الشغل الجارية وقت نشره.

المادة 2 مكررة

مقتضيات إضافية خاصة بأجراء القطاع الفلاحي دون سواهم.

الإمضاء: محمد السادس

---
<!-- page 2 -->

## مرسوم رقم 2.25.983 صادر في 29 ديسمبر 2025 (7 رجب 1447) بتطبيق الظهير الشريف رقم 1.25.67 المشار إليه.

الفصل 1

يحدد الحد الأدنى القانوني للأجر بالساعة في 17.92 درهما في القطاع غير الفلاحي.

الفصل 2

ينشر هذا المرسوم بالجريدة الرسمية للمملكة المغربية ويعمل به ابتداء من فاتح يناير 2026.

## بلاغ حول رحلات ممتدة

بلاغ بدون أي مواد.
"""
# the page-1 header line gives the issue number / date used for bo_number + valid_from
HEADER = "عدد 7485 - 5 جمادى الأولى 1447 (27 أكتوبر 2025)\n\n"


def _md(tmp_path):
    p = tmp_path / "BO_7485_Ar.md"
    p.write_text(HEADER + BO_MD, "utf-8")
    return p


def test_article_numbers_both_label_styles():
    assert parse_article_number("المادة الأولى")[0] == "1"
    assert parse_article_number("الفصل 12 مكررة")[0] == "12 bis"
    assert parse_article_number("المادة الحادية عشرة")[0] == "11"
    assert parse_article_number("المادة 2.13")[0] == "2.13"
    assert parse_article_number("المادة هذه")[0] is None


def test_bo_to_sources_structure_versions_edges(tmp_path):
    src, rep = bo_to_sources([_md(tmp_path)])
    ids = {i["instrument_id"] for i in src["instruments"]}
    assert ids == {"DAHIR_1.25.67", "DECREE_2.25.983"}
    nums = sorted((p["instrument_id"], p["number"]) for p in src["provisions"])
    assert ("DAHIR_1.25.67", "1") in nums and ("DAHIR_1.25.67", "11") in nums and ("DAHIR_1.25.67", "2 bis") in nums
    assert ("DECREE_2.25.983", "2") in nums  # الفصل handled as well as المادة
    v = src["provisions"][0]["versions"][0]
    assert v["valid_from"] == "2025-10-27" and v["valid_to"] is None and v["source"] == "BO_7485" and v["texts"]["ar"]["text"]
    assert any(e["type"] == "implements" and e["from"] == "DECREE_2.25.983" and e["to"] == "DAHIR_1.25.67" for e in src["edges"])
    assert any(e["type"] == "amends" for e in rep["unresolved_edges"])  # 1.03.194 is not in this run
    assert any(w["code"] == "effective_date_assumed" for w in rep["warnings"])


def test_builder_checks_run_on_the_output(tmp_path):
    src, _ = bo_to_sources([_md(tmp_path)])
    r = checks.Report()
    checks.check_sources(src, r)
    assert r.ok, r.errors
    assert all(v["_status"] == "single_source" for p in src["provisions"] for v in p["versions"])
    assert any(w["code"] == "numbering_gap" for w in r.warnings)  # 1, 2, 2 bis, 11 -> missing 3..10: reported, not hidden


def test_visual_order_arabic_is_refused(tmp_path):
    p = tmp_path / "BO_1_Ar.md"
    p.write_text("عدد 7000 - x (1 يناير 2026)\n\n## ظهير شريف رقم 1.1.1 صادر في x (1 يناير 2026) بكذا\n\nالمادة 1\n\nﻟﻨﺺ ﻣﻌﻜﻮس\n", "utf-8")
    src, rep = bo_to_sources([p])
    assert not src["provisions"] and "broken_arabic_order" in rep["skipped"][0]["reason"]


def test_freeze_pdfs_is_read_only_and_never_overwrites(tmp_path):
    srcd, fz = tmp_path / "pdf", tmp_path / "frozen"
    srcd.mkdir()
    (srcd / "BO_1_Ar.pdf").write_bytes(b"%PDF-1.4 original")
    r1 = freeze_pdfs(srcd, fz)
    assert r1["copied"] == 1 and (fz / "BO_1_Ar.pdf").stat().st_mode & 0o222 == 0
    m = json.loads((fz / "manifest.json").read_text())
    assert len(m["BO_1_Ar.pdf"]["sha256"]) == 64
    (srcd / "BO_1_Ar.pdf").write_bytes(b"%PDF-1.4 CHANGED")
    r2 = freeze_pdfs(srcd, fz)
    assert r2["changed_at_source"] == ["BO_1_Ar.pdf"] and (fz / "BO_1_Ar.pdf").read_bytes() == b"%PDF-1.4 original"
