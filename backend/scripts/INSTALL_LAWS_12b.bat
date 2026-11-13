@echo off
REM pack12b: court fees 1.84.54 (the one text pack12 could not add). Stop the backend first.
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_12b.json --install
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_12b.json
)
pause
