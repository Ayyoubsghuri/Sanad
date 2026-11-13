@echo off
REM pack16: civil procedure code 58.25, clean Adala text (644 articles). It replaces the scanned Bulletin Officiel copy.
REM Stop the backend first, restart it after.
REM   INSTALL_LAWS_16.bat          report only
REM   INSTALL_LAWS_16.bat install  add the Adala text, THEN hide the scanned copy (only if the add worked)
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_16.json --install
  py -m legalrag.builder.retire LAW_58.25 --all-dates
  echo.
  echo If the SUMMARY above says ADDED 644 articles, finish with:
  echo   py -m legalrag.builder.retire LAW_58.25 --all-dates --note "replaced by LAW_58.25_2026" --apply
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_16.json
)
pause
