@echo off
REM pack15: criminal procedure code 22.01, consolidated after law 03.23 (in force 2025-12-08). Stop the backend first, restart it after.
REM   INSTALL_LAWS_15.bat          report only (check the article counts)
REM   INSTALL_LAWS_15.bat install  add them to the pack (your older copy of 22.01 stays for dates before 2025-12-08)
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.retire LAW_22.01 --until 2025-12-08 --note "law 03.23 in force: 2025 consolidated edition installed" --apply
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_15.json --install
) else (
  py -m legalrag.builder.retire LAW_22.01 --until 2025-12-08
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_15.json
)
pause
