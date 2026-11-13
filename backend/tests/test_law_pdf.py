"""Law PDF importer: consolidated codes / laws that are not BO issues -> sources -> pack."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from legalrag.builder.append import append_sources
from legalrag.builder.from_law_pdf import clean_pages, fix_visual_order, law_pdf_to_sources, looks_reversed, parse_heading, split_articles
from legalrag.retrieval.embedders import HashingEmbedder
from legalrag.store.lawpack import LawPack


def test_heading_forms():
    assert parse_heading("المادة 5 - يجب على المشغل", "ar") == ("5", "المادة 5", "يجب على المشغل")
    assert parse_heading("المادة الأولى", "ar")[0] == "1"
    assert parse_heading("الفصل الحادي عشر: نص", "ar")[0] == "11"
    assert parse_heading("المادة 12 مكررة مرتين. يعاقب", "ar")[0] == "12 ter"
    assert parse_heading("المادة 2.13 يتم", "ar")[0] == "2.13"
    assert parse_heading("الفصل 214 يعتبر العقد", "ar")[0] == "214"
    assert parse_heading("Article 7 bis - Les parties", "fr")[0] == "7 bis"
    assert parse_heading("هذه مادة عادية", "ar") is None
    assert parse_heading("المادة82", "ar")[:2] == ("82", "المادة 82")  # the PDF text layer dropped the space (Family Code art. 82 was glued to art. 81)
    assert parse_heading("المادة82 عند حضور الطرفين", "ar")[0] == "82"


def test_visual_order_is_detected_and_repaired():
    assert looks_reversed("ةداملا ةداملا ةداملا ةداملا") and not looks_reversed("المادة المادة المادة")
    assert fix_visual_order("12 ةداملا") == "المادة 12"


def test_split_follows_the_numbering_and_keeps_the_chapter_path():
    pages = [
        ["فهرس", "المادة 1", "المادة 2", "المادة 3", "الباب الأول", "المادة 1", "الأولى الأحكام العامة تسري على الجميع.", "المادة 2 - يعرف الأجير بأنه كل شخص."],
        ["الباب الثاني", "المادة 3", "يجب على المشغل كذلك.", "المادة 10 من هذا القانون إحالة فقط", "المادة 4 - ينتهي العقد.", "الفصل الأول: أحكام خاصة", "المادة 5 مكرر - فقرة إضافية."],
    ]
    arts, rep = split_articles(pages, "ar")
    nums = [a.number for a in arts]
    assert nums == ["1", "2", "3", "4", "5 bis"] and rep["toc_discarded"] == 3
    a1 = next(a for a in arts if a.number == "1")
    assert "الأحكام العامة" in a1.body  # the TOC line "المادة 1" (empty) lost to the real article
    a3 = next(a for a in arts if a.number == "3")
    assert a3.path == "الباب الثاني" and "إحالة فقط" in a3.body  # the cross-reference line is text, not a new article
    assert any("10" in r["line"] for r in rep["refused_headings"])


def test_older_codes_use_fasl_for_articles():
    pages = [["الكتاب الأول", "الباب الأول", "الفصل 1", "نص الفصل الأول.", "الفصل 2", "نص الفصل الثاني.", "الفصل 3", "نص الفصل الثالث."]]
    arts, rep = split_articles(pages, "ar")
    assert rep["article_word"] == "الفصل" and [a.number for a in arts] == ["1", "2", "3"]
    assert arts[0].path == "الكتاب الأول / الباب الأول"


def test_page_furniture_is_removed():
    words = ["أولى", "ثانية", "ثالثة", "رابعة", "خامسة", "سادسة"]
    pages = [f"الجريدة الرسمية عدد {i}\nفقرة {w} فريدة\n{i}" for i, w in enumerate(words, start=1)]
    lines, rep = clean_pages(pages)
    assert all(len(pg) == 1 and pg[0].startswith("فقرة") for pg in lines) and rep["furniture_lines_dropped"] >= 12


def _arabic_pdf(tmp_path: Path) -> Path:
    pw = pytest.importorskip("playwright.sync_api")
    body = ("<h1>مدونة تجريبية</h1><h2>الباب الأول</h2><p>المادة الأولى</p><p>تطبق أحكام هذه المدونة على جميع الأجراء.</p>"
            "<p>المادة 2 - يعتبر أجيرا كل شخص التزم ببذل نشاطه.</p><p>المادة 3 - يجب على المشغل أن يسلم الأجير وثيقة.</p>"
            "<h2>الباب الثاني</h2><p>المادة 4 - تحدد مدة الشغل الأسبوعية.</p><p>المادة 5 - تمنح عطلة سنوية مؤدى عنها.</p>")
    html = f"<html dir='rtl' lang='ar'><body style='font-family:sans-serif;font-size:14pt'>{body}</body></html>"
    out = tmp_path / "code.pdf"
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.set_content(html)
            pg.pdf(path=str(out))
            b.close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no browser to make the sample PDF: {e}")
    return out


META = {"number": "99.01", "title_ar": "مدونة تجريبية", "kind": "law", "effective": "2004-06-08", "domain": "labor", "lang": "ar"}


def test_arabic_pdf_to_sources(tmp_path):
    pdf = _arabic_pdf(tmp_path)
    src, rep = law_pdf_to_sources(pdf, META, tmp_path / "frozen")
    assert not rep["problems"] and rep["articles"] == 5, rep
    nums = [p["number"] for p in src["provisions"]]
    assert nums == ["1", "2", "3", "4", "5"]
    texts = {p["number"]: p["versions"][0]["texts"]["ar"]["text"] for p in src["provisions"]}
    assert "الأجراء" in texts["1"] and "الأجير" in texts["3"]  # lam-alef survived the repair
    assert src["provisions"][3]["path"] == "الباب الثاني" and src["provisions"][0]["page"] == 1
    inst = src["instruments"][0]
    assert inst["instrument_id"] == "LAW_99.01" and inst["effective_date"] == "2004-06-08" and "consolidated" in inst["status_note"]
    s0 = src["sources"][0]
    assert s0["kind"] == "sgg_consolidated" and s0["url"].startswith("file:") and Path(s0["path"]).exists()


def test_french_pdf_roundtrip(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "fr.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    y = 800
    for line in ["Livre I", "Titre I", "Article 1 - Les parties sont libres de contracter.", "Article 2 - Le contrat est valable.", "Article 2 bis - Disposition ajoutee.",
                 "Article 3 - Fin du texte."]:
        c.drawString(60, y, line)
        y -= 24
    c.save()
    src, rep = law_pdf_to_sources(pdf, {**META, "lang": "fr", "number": "7.7", "title_fr": "Code test"})
    assert [p["number"] for p in src["provisions"]] == ["1", "2", "2 bis", "3"], rep
    assert src["provisions"][0]["path"].startswith("Livre I")
    assert list(src["provisions"][0]["versions"][0]["texts"]) == ["fr"]


def test_pdf_without_text_is_refused_with_a_reason(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    c.showPage()
    c.showPage()
    c.save()
    _src, rep = law_pdf_to_sources(pdf, META)
    assert rep["problems"] and any("scanned" in p or "no text" in p or "only 0" in p for p in rep["problems"])


def test_import_into_the_pack_and_find_it(tmp_path, pack_path):
    pdf = _arabic_pdf(tmp_path)
    src, rep = law_pdf_to_sources(pdf, META, tmp_path / "frozen")
    work = tmp_path / "w.db"
    shutil.copy2(pack_path, work)
    res = append_sources(work, src, HashingEmbedder(), "law-1")
    assert res["instruments"] == 1 and res["articles"] == 5
    p = LawPack(work)
    assert p.instrument("LAW_99.01")["title_ar"] == "مدونة تجريبية"
    assert p.keyword_search("عطله", date(2030, 1, 1), 5)  # normalised terms: the new text is searchable
    ver = p.version_at("LAW_99.01_ART_5", date(2030, 1, 1))
    assert ver is not None
    loc = p.article_location("LAW_99.01_ART_5", ver["pv_id"])
    assert loc and loc["url"].startswith("file:")  # the PDF page viewer can find the file
    p.close()
    db = sqlite3.connect(work)
    assert db.execute("SELECT kind FROM source_file WHERE url LIKE 'file:%'").fetchone()[0] == "sgg_consolidated"


def test_markdown_input_and_repealed_ranges(tmp_path):
    from legalrag.builder.from_law_pdf import clean_pages, read_pages, split_articles

    md = tmp_path / "c.md"
    md.write_text("<!-- page 1 -->\n\n> **NOTE:** LOW COVERAGE (40%)\n\n## الفصل 1\n\nنص الفصل الأول طويل بما يكفي.\n\n## الفصل 2\n\nنص الفصل الثاني طويل بما يكفي.\n\n## الفصول 3 إلى [^9]12\n\n## الفصل 13\n\nنص الفصل الثالث عشر.\n\n## الفصل 14\n\nنص آخر.\n", "utf-8")
    pages, info = read_pages(md)
    assert info["from_markdown"] and info["low_coverage_pages"] == [1]
    arts, rep = split_articles(clean_pages(pages)[0], "ar")
    assert [a.number for a in arts] == ["1", "2", "13", "14"]
    assert not rep["gaps"] or rep["gaps"] == []


def test_crosscheck_compare():
    from legalrag.builder.crosscheck_sgg import compare

    r = compare({"1": "يجب على المشغل أداء الأجر في الأجل المحدد", "2": "نص مختلف تماما هنا", "3": "فقط في المصدر الأول"},
                {"1": "يجب على المشغل أداء الأجر في الأجل المحدد.", "2": "كلام آخر لا علاقة له بالأول", "4": "فقط هنا"})
    assert r["only_sgg"] == ["3"] and r["only_pack"] == ["4"] and [d["article"] for d in r["differ"]] == ["2"]


def test_boct_passages_and_issue(tmp_path):
    from legalrag.builder.from_boct import issue_info, to_sources

    body = "\n\n".join(f"فقرة رقم {i} من قرار رئيس المجلس الجماعي تتضمن نصا طويلا بما يكفي لتكوين مقطع كامل من الجريدة " * 3 for i in range(30))
    md = tmp_path / "BOCT 62 fev 2025.md"
    md.write_text("<!-- page 4 -->\n\nالعدد الثاني و الستون 15 شعبان 1446 (14 فبراير 2025) الجريدة الرسمية للجماعات الترابية\n\n## جهة الشرق\n\n" + body + "\n\n<!-- page 5 -->\n\n" + body, "utf-8")
    assert issue_info(md.read_text("utf-8"), md.name)[1] == "2025-02-14"
    src, rep = to_sources(md)
    assert src and rep["passages"] >= 5 and src["instruments"][0]["instrument_id"].startswith("MA_BOCT_")
    assert all(len(p["versions"][0]["texts"]["ar"]["text"]) < 2600 for p in src["provisions"])


def test_batch_if_absent_markdown(tmp_path):
    from legalrag.builder.make_batch import consolidated_date

    assert consolidated_date("Version consolidée du 30/7/2025") == "2025-07-30"
    assert consolidated_date("صيغة موطدة بتاريخ 29يوليو 2024") == "2024-07-29"
    assert consolidated_date("صيغة موطدة بتاريخ سبتمبر 2026") == "2026-09-01"
