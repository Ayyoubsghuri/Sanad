@echo off
REM Correct the issue dates of the BOCT issues already installed (no re-embedding).
REM   FIX_BOCT_DATES.bat          show what would change
REM   FIX_BOCT_DATES.bat apply    write the corrections
cd /d "%~dp0.."
if "%1"=="apply" (
  py -m legalrag.builder.redate_boct data/boct --apply
) else (
  py -m legalrag.builder.redate_boct data/boct
)
pause
