@echo off
REM pack13: the laws and decrees from miss.rar. Stop the backend first, restart it after.
REM   INSTALL_LAWS_13.bat          report only (check the article counts)
REM   INSTALL_LAWS_13.bat install  add them to the pack
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_13.json --install
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_13.json
)
pause
