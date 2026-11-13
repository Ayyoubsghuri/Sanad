@echo off
cd /d "%~dp0.."
REM Criminal procedure code (data\cpp\cpp.pdf, pages 225-484).  Its text layer is corrupted, so it is read by OCR first.
REM Needs: pip install pypdfium2 pillow   +  Tesseract with ara.traineddata (tessdata_best).
REM Set TESSDATA to the folder that holds ara.traineddata:
set TESSDATA=C:\Program Files\Tesseract-OCR\tessdata
echo === test: 3 pages
py tools\ocr_pdf_pages.py data\cpp\cpp.pdf --from 225 --to 227 --tessdata "%TESSDATA%" --out data\cpp\cpp_test.md
echo Open data\cpp\cpp_test.md and check the Arabic reads well. Press a key to OCR all pages 225-484 (about 260 pages, several minutes on all cores).
pause
py tools\ocr_pdf_pages.py data\cpp\cpp.pdf --from 225 --to 484 --tessdata "%TESSDATA%" --out data\cpp\cpp_ocr.md
echo.
echo Now report on it (nothing installed):
py -m legalrag.builder.from_law_pdf --batch batches/codes.json
echo.
echo If criminal procedure shows about 750+ articles starting at article 1: run scripts\INSTALL_CODES_AND_SGG.bat to install (the other codes are skipped if already installed).
pause
