@echo off
REM pack12: the laws and decrees from New_folder.rar. Stop the backend first, restart it after.
REM   INSTALL_LAWS_12.bat          report only (check the article counts)
REM   INSTALL_LAWS_12.bat install  add them to the pack (the 2013 text of 43.12 stays for dates before 2021-07-29)
cd /d "%~dp0.."
if "%1"=="install" (
  py -m legalrag.builder.retire LAW_43.12 --until 2021-07-29 --note "2021 consolidated edition installed" --apply
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_12.json --install
) else (
  py -m legalrag.builder.retire LAW_43.12 --until 2021-07-29
  py -m legalrag.builder.from_law_pdf --batch batches/add_laws_12.json
)
pause
