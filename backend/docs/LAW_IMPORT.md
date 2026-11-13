# Adding laws from PDF (codes, the Constitution, older laws)

The update button reads Bulletin Officiel issues. For laws that are not in the issues you loaded, use the PDF importer. One law = one PDF.

## One law
    py -m legalrag.builder.from_law_pdf "C:\laws\65.99.pdf" --number 65.99 --title "مدونة الشغل" --effective 2004-06-08 --domain labor --dump C:\laws\65.99.txt

This only PRINTS A REPORT: pages, articles found, first and last article, numbering gaps, headings it refused. Open the `--dump` text file and read a few
articles. If the report is right, run the same command again with `--install` (stop the backend first, start it again afterwards).

## Many laws
Copy `batches/template_laws_to_add.json`, fill `file` and `effective`, then:

    py -m legalrag.builder.from_law_pdf --batch batches/template_laws_to_add.json            (report on every file)
    py -m legalrag.builder.from_law_pdf --batch batches/template_laws_to_add.json --install  (add the good ones, list the others)

## What the report tells you
* ARTICLES FOUND vs the real count: pass `--official-articles N` to be warned when they differ.
* numbering gaps: missing article numbers (a heading the reader could not recognise, or an article the law really skipped).
* headings refused: lines like "المادة 12 من هذا القانون" in the middle of a text; they stay inside the article before them.
* PROBLEM lines: no text layer (a scan: it needs OCR first), too few articles, or no date.

## Notes
* A consolidated PDF is the text up to its own date: later amendments are not in it. Give `--consolidated-on` when you know it.
* Domains: civil_procedure, commercial, criminal, family, labor, legal_profession, obligations, property, tax, traffic, other.
* Already in the pack under the same kind and number: the importer refuses; nothing is overwritten.
