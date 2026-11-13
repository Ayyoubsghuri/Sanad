@echo off
REM pack18: Penal Code (updated 2024-08-22, includes 43.22 alternative sentences; applies from 2025-08-22) and DOC (updated 2024-08-22).
REM Stop the backend first, restart it after.
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_18.json --install
  py -m legalrag.builder.retire DAHIR_1.59.413 --until 2025-08-22
  py -m legalrag.builder.retire DAHIR_DOC-1913 --until 2024-08-22
  echo.
  echo If the SUMMARY above says ADDED for both texts, finish with:
  echo   py -m legalrag.builder.retire DAHIR_1.59.413 --until 2025-08-22 --note "2024 consolidated edition installed" --apply
  echo   py -m legalrag.builder.retire DAHIR_DOC-1913 --until 2024-08-22 --note "2024 consolidated edition installed" --apply
) else (
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_18.json
)
pause
