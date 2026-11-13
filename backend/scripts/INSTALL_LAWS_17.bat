@echo off
REM pack17: Commerce Code 15.95 (updated 2026-01-29), Labour Code 65.99 (updated 2026-07-16) and 13 decrees applying them.
REM Stop the backend first, restart it after.
REM   INSTALL_LAWS_17.bat          report only
REM   INSTALL_LAWS_17.bat install  add them, THEN end the old copies of the two codes on the dates of the new editions
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_17.json --install
  py -m legalrag.builder.retire LAW_15.95 --until 2026-01-29
  py -m legalrag.builder.retire LAW_65.99 --until 2026-07-16
  echo.
  echo If the SUMMARY above says ADDED 849 articles for 15.95 and ADDED 589 for 65.99, finish with:
  echo   py -m legalrag.builder.retire LAW_15.95 --until 2026-01-29 --note "2026 consolidated edition installed" --apply
  echo   py -m legalrag.builder.retire LAW_65.99 --until 2026-07-16 --note "2026 consolidated edition installed" --apply
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_17.json
)
pause
