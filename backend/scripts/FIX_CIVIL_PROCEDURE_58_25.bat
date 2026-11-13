@echo off
REM Law 58.25 (new civil procedure) applies from 2026-08-24 and repeals (art. 644) the old code and laws 41.90, 53.95, 80.03.
REM Stop the backend first, restart it after.
REM   FIX_CIVIL_PROCEDURE_58_25.bat          report only
REM   FIX_CIVIL_PROCEDURE_58_25.bat install  apply
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.redate LAW_58.25 --from 2026-08-24 --note "entry into force, 6 months after BO 7485" --apply
  py -m legalrag.builder.retire DAHIR_1.74.447 LAW_41.90 LAW_53.95 LAW_80.03 --until 2026-08-24 --note "repealed by art. 644 of law 58.25" --apply
) else (
  py -m legalrag.builder.redate LAW_58.25 --from 2026-08-24
  py -m legalrag.builder.retire DAHIR_1.74.447 LAW_41.90 LAW_53.95 LAW_80.03 --until 2026-08-24
)
pause
