@echo off
REM Law 103.13 (violence against women). Stop the backend first, restart it after.
cd /d "%~dp0.."
py -m legalrag.builder.from_law_pdf --batch batches/add_103_13.json --install
pause
