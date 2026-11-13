@echo off
REM pack9: the laws from Downloads_1.rar. Stop the backend first, restart it after.
REM   INSTALL_LAWS_9.bat          report only (check the article counts)
REM   INSTALL_LAWS_9.bat install  hide the old civil-status decree 2.99.665, then add the laws to the pack
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.retire DECREE_2.99.665 --all-dates --note "2020 consolidated edition installed" --apply
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_9.json --install
) else (
  py -m legalrag.builder.retire DECREE_2.99.665 --all-dates
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_9.json
)
pause
