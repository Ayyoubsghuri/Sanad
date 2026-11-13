@echo off
REM Run from anywhere (double-click or from the (env) prompt). It moves to the backend folder first.
cd /d "%~dp0.."
echo === 1/4  the 8 codes (data\codes + data\cpp): report only
py -m legalrag.builder.from_law_pdf --batch batches/codes.json
echo.
echo Look at the SUMMARY above. Press a key to INSTALL the codes, or close the window to stop.
pause
py -m legalrag.builder.from_law_pdf --batch batches/codes.json --install
echo.
echo === 2/4  the 66 SGG consolidated texts (data\sgg). Laws already in the pack are skipped.
py -m legalrag.builder.make_batch data/sgg --out batches/sgg.json
py -m legalrag.builder.from_law_pdf --batch batches/sgg.json --install
echo.
echo === 3/4  laws in the pack that amend the codes after their text date  ->  reports\amendments_report.json
py -m legalrag.builder.find_amendments batches/codes.json
echo.
echo === 4/4  SGG text vs the same law already in the pack  ->  reports\crosscheck_report.json
py -m legalrag.builder.crosscheck_sgg data/sgg
echo.
echo Done. Restart legalrag.
pause
