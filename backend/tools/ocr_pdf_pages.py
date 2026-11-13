#!/usr/bin/env python3
"""OCR a page range of a PDF with Tesseract (Arabic) on several CPU cores -> a .md with `<!-- page N -->` markers, ready for the law importer.

    py tools\\ocr_pdf_pages.py data\\cpp\\cpp.pdf --from 225 --to 484 --tessdata C:\\path\\to\\tessdata_best --out data\\cpp\\cpp_ocr.md

Needs: pip install pypdfium2 pillow   and Tesseract installed (the same one your scripts\\ocr_scanned.py uses), with ara.traineddata (tessdata_best).
Page numbers in the output are the PDF's own page numbers (so page images line up).  Run with --from 225 --to 228 first to look at 3 pages."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


def _one(args):
    pdf, i, dpi, tess, tessdir, psm = args
    import pypdfium2 as pdfium

    d = pdfium.PdfDocument(pdf)
    img = d[i - 1].render(scale=dpi / 72).to_pil().convert("L")
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(tmp)
    cmd = [tess, tmp, "-", "-l", "ara", "--psm", str(psm)] + (["--tessdata-dir", tessdir] if tessdir else [])
    txt = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8").stdout.strip()
    os.remove(tmp)
    return i, txt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--from", dest="first", type=int, default=1)
    ap.add_argument("--to", dest="last", type=int, default=0, help="last page (default: the end)")
    ap.add_argument("--tessdata", help="folder holding ara.traineddata (tessdata_best)")
    ap.add_argument("--tesseract", default="tesseract", help="path of tesseract.exe if it is not on PATH")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--out")
    a = ap.parse_args()
    import pypdfium2 as pdfium

    n = len(pdfium.PdfDocument(a.pdf))
    last = min(a.last or n, n)
    out = Path(a.out) if a.out else Path(a.pdf).with_name(Path(a.pdf).stem + "_ocr.md")
    jobs = [(a.pdf, i, a.dpi, a.tesseract, a.tessdata, a.psm) for i in range(a.first, last + 1)]
    res: dict[int, str] = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for k, (i, t) in enumerate(ex.map(_one, jobs), start=1):
            res[i] = t
            if k % 10 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} pages", file=sys.stderr, flush=True)
    parts = ["> **NOTE:** OCR (Tesseract ara, %d dpi) of pages %d-%d: expect isolated letter errors; verify a word or number against the page image.\n" % (a.dpi, a.first, last)]
    for i in range(a.first, last + 1):
        parts.append(f"\n---\n<!-- page {i} -->\n\n{res.get(i, '')}\n")
    out.write_text("".join(parts), encoding="utf-8")
    print("written", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
