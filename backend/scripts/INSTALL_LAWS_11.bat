@echo off
REM pack11: 2024 consolidated insurance code 17.99 and co-ownership 18.00 (Adala), + the 2002 text of 18.00 for 2003-2016.
REM Stop the backend first, restart it after.
REM   INSTALL_LAWS_11.bat          report only
REM   INSTALL_LAWS_11.bat install  install
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.retire LAW_17.99 --until 2024-08-22 --note "2024 consolidated edition installed" --apply
  py -m legalrag.builder.retire LAW_18.00 --all-dates --note "SGG copy with low OCR coverage; Adala 2024 edition installed" --apply
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_11.json --install
  py -m legalrag.builder.retire LAW_18.00_2002 --until 2016-05-16 --note "amended by law 106.12" --apply
) else (
  py -m legalrag.builder.retire LAW_17.99 --until 2024-08-22
  py -m legalrag.builder.retire LAW_18.00 --all-dates
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_11.json
)
pause
