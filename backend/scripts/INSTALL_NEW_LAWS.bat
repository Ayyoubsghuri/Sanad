@echo off
REM New laws from Downloads.rar (OCR-checked text). Stop the backend first, restart it after.
REM   INSTALL_NEW_LAWS.bat          report only (check the article counts)
REM   INSTALL_NEW_LAWS.bat install  add them to the pack
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_new_laws.json --install
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_new_laws.json
)
pause
