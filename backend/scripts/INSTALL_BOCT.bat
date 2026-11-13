@echo off
REM The 47 local-authority gazettes (data\boct). ~12,000 passages.
REM   INSTALL_BOCT.bat            report only
REM   INSTALL_BOCT.bat 62,63      install only issues 62 and 63
REM   INSTALL_BOCT.bat all        install everything
cd /d "%~dp0.."
if "%1"=="" (
  py -m legalrag.builder.from_boct data/boct
) else if "%1"=="all" (
  py -m legalrag.builder.from_boct data/boct --install
) else (
  py -m legalrag.builder.from_boct data/boct --install --only %*
)
pause
