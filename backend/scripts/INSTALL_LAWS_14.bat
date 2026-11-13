@echo off
REM pack14: social security dahir 1.72.184 (2025 consolidated, includes job-loss compensation) and decree 2.25.266. Stop the backend first, restart it after.
REM   INSTALL_LAWS_14.bat          report only (check the article counts)
REM   INSTALL_LAWS_14.bat install  add them to the pack (your older copy of 1.72.184 stays for dates before 2025-03-03)
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.retire DAHIR_1.72.184 --until 2025-03-03 --note "2025 consolidated edition installed" --apply
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_14.json --install
) else (
  py -m legalrag.builder.retire DAHIR_1.72.184 --until 2025-03-03
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_14.json
)
pause
