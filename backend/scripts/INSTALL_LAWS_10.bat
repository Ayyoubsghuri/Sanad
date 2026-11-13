@echo off
REM pack10: 4 laws read from BO 5054 (7 Nov 2002). Stop the backend first, restart it after.
REM   INSTALL_LAWS_10.bat          report only
REM   INSTALL_LAWS_10.bat install  add them to the pack
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_10.json --install
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_10.json
)
pause
