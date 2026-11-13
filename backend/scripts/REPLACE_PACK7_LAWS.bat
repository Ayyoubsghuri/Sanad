@echo off
REM ONLY if you installed pack7.zip (INSTALL_10_LAWS) before: hides those 10 old copies and installs the corrected ones.
REM Stop the backend first, restart it after.
cd /d "%~dp0.."
py -m legalrag.builder.retire DAHIR_1.58.008 LAW_01.03 LAW_31.13 LAW_62.99 LAW_17.95 LAW_5.96 LAW_09.08 LAW_88.13 LAW_51.17 DAHIR_1.72.184 --all-dates --note "corrected copy installed" --apply
py -m legalrag.builder.from_law_pdf --batch batches/replace_pack7.json --install
pause
