@echo off
REM Family Code art. 82 was glued into art. 81. Installs the corrected text as LAW_70.03_R1, then hides the old LAW_70.03.
REM Stop the backend first, restart it after.
cd /d "%~dp0.."
py -m legalrag.builder.from_law_pdf --batch batches/reimport_family.json
echo.
echo Look at the report above (400 articles, 0 gaps). Press a key to INSTALL, or close the window to stop.
pause
py -m legalrag.builder.from_law_pdf --batch batches/reimport_family.json --install
py -m legalrag.builder.retire LAW_70.03 --all-dates --note "replaced by corrected import R1" --apply
py tools\show_articles.py LAW_70.03_R1 81 82
pause
